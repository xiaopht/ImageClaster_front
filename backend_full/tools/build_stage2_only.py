from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from texture_color_pipeline.config import IMAGE_SUFFIXES, SOURCE_NAMES, PipelineConfig
from texture_color_pipeline.dinov3_features import DualDinoExtractor
from texture_color_pipeline.image_ops import load_rgb_image, stage2_variant_views


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


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_stage2_source(
    config: PipelineConfig,
    source: str,
    classes: Dict[str, List[Path]],
    extractor: DualDinoExtractor,
    skip_existing: bool,
) -> dict:
    vit_dir = config.source_stage2_vit_feature_dir(source)
    conv_dir = config.source_stage2_conv_feature_dir(source)
    vit_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"root": str(config.source_root(source)), "classes": {}}
    for index, pattern_id in enumerate(sorted(classes.keys()), start=1):
        vit_path = vit_dir / f"{pattern_id}.pt"
        conv_path = conv_dir / f"{pattern_id}.pt"
        if skip_existing and vit_path.exists() and conv_path.exists():
            print(f"[{source} {index}/{len(classes)}] skip {pattern_id}", flush=True)
            manifest["classes"][pattern_id] = {
                "reference_images": len(classes[pattern_id]),
                "stage2_variant_templates": None,
                "skipped_existing": True,
            }
            continue
        print(f"[{source} {index}/{len(classes)}] build {pattern_id}", flush=True)
        vit_parts = []
        conv_parts = []
        for image_path in classes[pattern_id]:
            image = load_rgb_image(image_path)
            views = stage2_variant_views(
                image,
                source=source,
                realshot_white_balance=config.stage2_realshot_white_balance,
                realshot_color_normalize=config.stage2_realshot_color_normalize,
                sample_mode=config.stage2_realshot_sample_mode,
            )
            vit_features, conv_features = extractor.extract_dual(views)
            vit_parts.append(vit_features)
            conv_parts.append(conv_features)
        vit_tensor = torch.cat(vit_parts, dim=0)
        conv_tensor = torch.cat(conv_parts, dim=0)
        torch.save(vit_tensor.half().cpu(), vit_path)
        torch.save(conv_tensor.half().cpu(), conv_path)
        manifest["classes"][pattern_id] = {
            "reference_images": len(classes[pattern_id]),
            "stage2_variant_templates": int(vit_tensor.shape[0]),
            "skipped_existing": False,
        }
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scan-root", type=Path, required=True)
    parser.add_argument("--realshot-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--model-vit", type=Path, required=True)
    parser.add_argument("--model-conv", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args()

    config = PipelineConfig(
        scan_root=args.scan_root.resolve(),
        realshot_root=args.realshot_root.resolve(),
        output_root=args.output_root.resolve(),
        model_vit=args.model_vit.resolve(),
        model_conv=args.model_conv.resolve(),
        batch_size=args.batch_size,
        stage2_realshot_white_balance=False,
        stage2_realshot_color_normalize=False,
        stage2_realshot_sample_mode="none",
    )
    extractor = DualDinoExtractor(config)
    source_classes = {
        "scan": discover_reference_images(config.scan_root),
        "realshot": discover_reference_images(config.realshot_root),
    }
    manifest = {
        "created_at": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "pipeline": "stage2_variant_dino_only",
        "preprocessing": {
            "white_balance": False,
            "color_normalize": False,
            "sample_mode": "none",
        },
        "sources": {},
    }
    for source in SOURCE_NAMES:
        manifest["sources"][source] = build_stage2_source(
            config,
            source,
            source_classes.get(source, {}),
            extractor,
            skip_existing=not args.rebuild,
        )
    save_json(config.output_root / "stage2_variant_manifest.json", manifest)


if __name__ == "__main__":
    main()
