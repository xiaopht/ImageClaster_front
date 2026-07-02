from __future__ import annotations

import argparse
import gc
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import torch
import torch.nn.functional as F

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from texture_color_pipeline.config import IMAGE_SUFFIXES, SOURCE_NAMES, PipelineConfig, pattern_family_id
from texture_color_pipeline.dinov3_features import DualDinoExtractor
from texture_color_pipeline.gallery import save_json
from texture_color_pipeline.image_ops import (
    average_color_descriptors,
    color_descriptor,
    load_rgb_image,
    reference_texture_templates,
    stage2_variant_views,
)


def discover_reference_images(root: Path) -> Dict[str, List[Path]]:
    classes: Dict[str, List[Path]] = {}
    if not root.exists():
        return classes
    for pattern_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        images = sorted(
            path for path in pattern_dir.rglob("*") if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
        )
        if images:
            classes[pattern_dir.name] = images
    return classes


def catalog_available(decor_root: Path, pattern_id: str) -> bool:
    pattern_dir = decor_root / pattern_id
    if not pattern_dir.exists():
        return False
    return any((pattern_dir / name).exists() for name in ("metadata.json", "bigImage.jpg", "bigImage.png"))


def build_source_gallery(
    config: PipelineConfig,
    source: str,
    classes: Dict[str, List[Path]],
    extractor: DualDinoExtractor,
    limit: int | None,
    skip_existing: bool,
) -> dict:
    source_vit_dir = config.source_vit_feature_dir(source)
    source_conv_dir = config.source_conv_feature_dir(source)
    source_stage2_vit_dir = config.source_stage2_vit_feature_dir(source)
    source_stage2_conv_dir = config.source_stage2_conv_feature_dir(source)
    source_color_dir = config.source_color_descriptor_dir(source)
    source_vit_dir.mkdir(parents=True, exist_ok=True)
    source_conv_dir.mkdir(parents=True, exist_ok=True)
    source_stage2_vit_dir.mkdir(parents=True, exist_ok=True)
    source_stage2_conv_dir.mkdir(parents=True, exist_ok=True)
    source_color_dir.mkdir(parents=True, exist_ok=True)

    pattern_ids = sorted(classes.keys())
    if limit:
        pattern_ids = pattern_ids[:limit]

    source_manifest = {
        "root": str(config.source_root(source)),
        "classes": {},
    }

    for index, pattern_id in enumerate(pattern_ids, start=1):
        vit_path = source_vit_dir / f"{pattern_id}.pt"
        conv_path = source_conv_dir / f"{pattern_id}.pt"
        stage2_vit_path = source_stage2_vit_dir / f"{pattern_id}.pt"
        stage2_conv_path = source_stage2_conv_dir / f"{pattern_id}.pt"
        color_path = source_color_dir / f"{pattern_id}.json"
        if (
            skip_existing
            and vit_path.exists()
            and conv_path.exists()
            and stage2_vit_path.exists()
            and stage2_conv_path.exists()
            and color_path.exists()
        ):
            print(f"[{source} {index}/{len(pattern_ids)}] skip existing {pattern_id}")
            source_manifest["classes"][pattern_id] = {
                "family_id": pattern_family_id(pattern_id),
                "reference_images": len(classes[pattern_id]),
                "templates": None,
                "catalog_available": catalog_available(config.decor_root, pattern_id),
                "skipped_existing": True,
            }
            continue

        print(f"[{source} {index}/{len(pattern_ids)}] build {pattern_id}")
        vit_parts = []
        conv_parts = []
        stage2_vit_parts = []
        stage2_conv_parts = []
        color_parts = []
        for image_path in classes[pattern_id]:
            image = load_rgb_image(image_path)
            templates = reference_texture_templates(image)
            if len(templates) != config.templates_per_image:
                raise RuntimeError(
                    f"{pattern_id}: expected {config.templates_per_image} templates, got {len(templates)}"
                )
            vit_features, conv_features = extractor.extract_dual(templates)
            vit_parts.append(vit_features)
            conv_parts.append(conv_features)
            stage2_views = stage2_variant_views(
                image,
                source=source,
                realshot_white_balance=config.stage2_realshot_white_balance,
                realshot_color_normalize=config.stage2_realshot_color_normalize,
                sample_mode=config.stage2_realshot_sample_mode,
            )
            stage2_vit_features, stage2_conv_features = extractor.extract_dual(stage2_views)
            stage2_vit_parts.append(stage2_vit_features)
            stage2_conv_parts.append(stage2_conv_features)
            color_parts.append(color_descriptor(image))

        vit_tensor = torch.cat(vit_parts, dim=0)
        conv_tensor = torch.cat(conv_parts, dim=0)
        stage2_vit_tensor = torch.cat(stage2_vit_parts, dim=0)
        stage2_conv_tensor = torch.cat(stage2_conv_parts, dim=0)
        torch.save(vit_tensor.cpu(), vit_path)
        torch.save(conv_tensor.cpu(), conv_path)
        torch.save(stage2_vit_tensor.cpu(), stage2_vit_path)
        torch.save(stage2_conv_tensor.cpu(), stage2_conv_path)
        save_json(color_path, average_color_descriptors(color_parts))

        source_manifest["classes"][pattern_id] = {
            "family_id": pattern_family_id(pattern_id),
                "reference_images": len(classes[pattern_id]),
                "templates": int(vit_tensor.shape[0]),
                "stage2_variant_templates": int(stage2_vit_tensor.shape[0]),
                "catalog_available": catalog_available(config.decor_root, pattern_id),
                "skipped_existing": False,
            }

    return source_manifest


def load_feature_tensor(path: Path) -> torch.Tensor:
    tensor = torch.load(path, map_location="cpu")
    if isinstance(tensor, dict):
        tensor = tensor.get("features")
    if not isinstance(tensor, torch.Tensor):
        raise RuntimeError(f"Feature file is not a tensor: {path}")
    if tensor.ndim != 2:
        raise RuntimeError(f"Feature tensor must be [N, D], got {tuple(tensor.shape)}: {path}")
    return F.normalize(tensor.float(), p=2, dim=1)


def build_scan_family_prototypes(config: PipelineConfig) -> dict:
    output_pairs = [
        (config.source_vit_feature_dir("scan"), config.scan_family_vit_feature_dir()),
        (config.source_conv_feature_dir("scan"), config.scan_family_conv_feature_dir()),
    ]
    summary: dict = {}
    for source_dir, target_dir in output_pairs:
        target_dir.mkdir(parents=True, exist_ok=True)
        grouped: Dict[str, dict] = {}
        for feature_path in sorted(source_dir.glob("*.pt")):
            tensor = load_feature_tensor(feature_path)
            if tensor.shape[0] % config.templates_per_image != 0:
                print(f"[family-prototype] skip non-aligned feature count: {feature_path}")
                continue
            family_id = pattern_family_id(feature_path.stem)
            templates = tensor.reshape(-1, config.templates_per_image, tensor.shape[1])
            entry = grouped.setdefault(
                family_id,
                {
                    "sum": torch.zeros(
                        (config.templates_per_image, tensor.shape[1]),
                        dtype=torch.float32,
                    ),
                    "count": 0,
                },
            )
            entry["sum"] += templates.sum(dim=0)
            entry["count"] += int(templates.shape[0])
            del tensor, templates
            gc.collect()

        model_summary = {}
        for family_id, entry in sorted(grouped.items()):
            if entry["count"] <= 0:
                continue
            prototype = F.normalize(entry["sum"] / float(entry["count"]), p=2, dim=1)
            torch.save(prototype.half().cpu(), target_dir / f"{family_id}.pt")
            model_summary[family_id] = {
                "source_patterns_or_images": int(entry["count"]),
                "templates": int(prototype.shape[0]),
            }
            del prototype
        summary[target_dir.name] = model_summary
        print(f"[family-prototype] wrote {len(model_summary)} families to {target_dir}")
    return summary


def build_gallery(config: PipelineConfig, limit: int | None = None, skip_existing: bool = True) -> dict:
    extractor = DualDinoExtractor(config)
    source_classes = {source: discover_reference_images(config.source_root(source)) for source in SOURCE_NAMES}
    if not any(source_classes.values()):
        raise FileNotFoundError(
            f"No source images found. scan_root={config.scan_root}; realshot_root={config.realshot_root}"
        )

    manifest = {
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "pipeline": "texture_first_color_second",
        "scan_root": str(config.scan_root),
        "realshot_root": str(config.realshot_root),
        "decor_root": str(config.decor_root),
        "models": {"vit": str(config.model_vit), "convnext": str(config.model_conv)},
        "templates_per_image": config.templates_per_image,
        "local_top_k": config.local_top_k,
        "source_weights": {
            "texture": config.texture_source_weights(),
            "stage2_variant": config.stage2_variant_source_weights(),
            "descriptor_color": config.color_source_weights(),
        },
        "rotation_padding_removed": True,
        "texture_preprocessing": "grayscale_autocontrast_equalize_unsharp",
        "color_preprocessing": "same_for_scan_and_realshot: gray_world_white_balance_center_92_percent_lab_descriptor",
        "stage2_variant_preprocessing": {
            "scan": "rgb_center_or_stable_region",
            "realshot_white_balance": config.stage2_realshot_white_balance,
            "realshot_color_normalize": config.stage2_realshot_color_normalize,
            "realshot_sample_mode": config.stage2_realshot_sample_mode,
        },
        "classes": {},
        "sources": {},
    }

    for source in SOURCE_NAMES:
        classes = source_classes[source]
        if not classes:
            print(f"[{source}] no images found under {config.source_root(source)}, skip")
            continue
        source_manifest = build_source_gallery(config, source, classes, extractor, limit, skip_existing)
        manifest["sources"][source] = source_manifest
        for pattern_id, source_info in source_manifest["classes"].items():
            item = manifest["classes"].setdefault(
                pattern_id,
                {
                    "family_id": pattern_family_id(pattern_id),
                    "catalog_available": catalog_available(config.decor_root, pattern_id),
                    "sources": {},
                },
            )
            item["sources"][source] = source_info

    manifest["scan_family_prototypes"] = build_scan_family_prototypes(config)

    save_json(config.manifest_path, manifest)
    print(f"Manifest written: {config.manifest_path}")
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build texture-first/color-second feature gallery.")
    parser.add_argument("--scan-root", type=Path, default=None)
    parser.add_argument("--realshot-root", type=Path, default=None)
    parser.add_argument("--reference-root", type=Path, default=None, help="Compatibility alias for --scan-root.")
    parser.add_argument("--decor-root", type=Path, default=None)
    parser.add_argument("--output-root", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None, help="Optional quick-test class limit.")
    parser.add_argument("--rebuild", action="store_true", help="Recompute existing feature files.")
    parser.add_argument("--batch-size", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scan_root = args.scan_root or args.reference_root
    config = PipelineConfig(
        scan_root=scan_root.resolve() if scan_root else PipelineConfig().scan_root,
        realshot_root=args.realshot_root.resolve() if args.realshot_root else PipelineConfig().realshot_root,
        decor_root=args.decor_root.resolve() if args.decor_root else PipelineConfig().decor_root,
        output_root=args.output_root.resolve() if args.output_root else PipelineConfig().output_root,
        batch_size=args.batch_size if args.batch_size else PipelineConfig().batch_size,
    )
    build_gallery(config, limit=args.limit, skip_existing=not args.rebuild)


if __name__ == "__main__":
    main()
