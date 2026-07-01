from __future__ import annotations

import argparse
import base64
import io
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import List, Optional

import torch
import torch.nn.functional as F
from PIL import Image

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from texture_color_pipeline.config import PipelineConfig, pattern_family_id
from texture_color_pipeline.dinov3_features import DualDinoExtractor
from texture_color_pipeline.gallery import (
    aggregate_reference_score,
    combine_texture_source_scores,
    fused_pattern_scores,
    load_json,
    load_source_color_descriptors,
    load_source_feature_banks,
    rerank_variants_with_color,
    restrict_to_ids,
    top_texture_families,
)
from texture_color_pipeline.image_ops import color_descriptor, load_rgb_image, query_texture_views
from texture_color_pipeline.train_texture_metric import ProjectionHead


BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def safe_foreground_crop(image: Image.Image, shrink_margin: float = 0.08) -> Image.Image:
    """Mild version of the existing upload crop; falls back to the original image."""
    try:
        from rembg import new_session, remove

        no_bg = remove(image, session=new_session(), post_process_mask=True)
        bbox = no_bg.getbbox()
        if not bbox:
            return image
        left, top, right, bottom = bbox
        width, height = right - left, bottom - top
        area_ratio = (width * height) / max(1, image.width * image.height)
        if area_ratio < 0.12:
            return image
        left += int(width * shrink_margin)
        top += int(height * shrink_margin)
        right -= int(width * shrink_margin)
        bottom -= int(height * shrink_margin)
        if right <= left or bottom <= top:
            return image
        return image.crop((left, top, right, bottom))
    except Exception:
        return image


def image_to_base64(image: Image.Image, size: int = 420) -> str:
    preview = image.copy()
    preview.thumbnail((size, size))
    output = io.BytesIO()
    preview.save(output, format="JPEG", quality=82)
    return "data:image/jpeg;base64," + base64.b64encode(output.getvalue()).decode("utf-8")


class TextureColorRecognizer:
    def __init__(self, config: PipelineConfig) -> None:
        self.config = config
        self.manifest = load_json(config.manifest_path) if config.manifest_path.exists() else {}
        self.source_banks = load_source_feature_banks(config)
        self.color_descriptors_by_source = load_source_color_descriptors(config)
        self.extractor = DualDinoExtractor(config)
        self.metric_head = None
        self.metric_banks_by_source = {}
        self.load_metric_head()

    def load_metric_head(self) -> None:
        if not self.config.metric_head_path.exists():
            return
        checkpoint = torch.load(self.config.metric_head_path, map_location="cpu")
        head = ProjectionHead(int(checkpoint["input_dim"]), int(checkpoint["embedding_dim"]))
        head.load_state_dict(checkpoint["projection_state"])
        head.eval()
        self.metric_head = head
        for source, banks in self.source_banks.items():
            source_metric_bank = {}
            vit_bank = banks["vit"]
            conv_bank = banks["conv"]
            for pattern_id in sorted(set(vit_bank.keys()) & set(conv_bank.keys())):
                count = min(vit_bank[pattern_id].shape[0], conv_bank[pattern_id].shape[0])
                if count == 0:
                    continue
                combined = F.normalize(
                    torch.cat([vit_bank[pattern_id][:count], conv_bank[pattern_id][:count]], dim=1).float(),
                    p=2,
                    dim=1,
                )
                with torch.inference_mode():
                    source_metric_bank[pattern_id] = head(combined)
            self.metric_banks_by_source[source] = source_metric_bank

    def ready_status(self) -> dict:
        source_status = {}
        for source, banks in self.source_banks.items():
            source_status[source] = {
                "vit_classes": len(banks["vit"]),
                "conv_classes": len(banks["conv"]),
                "color_descriptors": len(self.color_descriptors_by_source.get(source, {})),
                "metric_classes": len(self.metric_banks_by_source.get(source, {})),
            }
        return {
            "manifest_present": self.config.manifest_path.exists(),
            "metric_head_loaded": self.metric_head is not None,
            "sources": source_status,
            "feature_root": str(self.config.output_root),
            "texture_top_families": self.config.texture_top_families,
            "source_weights": {
                "texture": self.config.texture_source_weights(),
                "stage2_variant": self.config.stage2_variant_source_weights(),
                "descriptor_color": self.config.color_source_weights(),
                "stage2": self.config.stage2_score_weights(),
            },
        }

    def metric_pattern_scores(self, query_vit: torch.Tensor, query_conv: torch.Tensor, config: PipelineConfig) -> List[dict]:
        if self.metric_head is None:
            return []
        count = min(query_vit.shape[0], query_conv.shape[0])
        query_combined = F.normalize(torch.cat([query_vit[:count], query_conv[:count]], dim=1), p=2, dim=1)
        with torch.inference_mode():
            query_metric = self.metric_head(query_combined)
        classes = self.manifest.get("classes", {})
        source_results = {}
        for source, metric_bank in self.metric_banks_by_source.items():
            results = []
            for pattern_id, reference_metric in metric_bank.items():
                score = aggregate_reference_score(
                    query_metric,
                    reference_metric,
                    config.templates_per_image,
                    config.local_top_k,
                )
                results.append(
                    {
                        "pattern_id": pattern_id,
                        "family_id": classes.get(pattern_id, {}).get("family_id") or pattern_family_id(pattern_id),
                        "texture_score": float(score),
                        "metric_score": float(score),
                        "vit_score": None,
                        "convnext_score": None,
                        "available_models": 1,
                    }
                )
            source_results[source] = results
        return combine_texture_source_scores(source_results, config.texture_source_weights(), self.manifest)

    def build_score_config(
        self,
        texture_scan_weight: float | None = None,
        texture_realshot_weight: float | None = None,
        color_scan_weight: float | None = None,
        color_realshot_weight: float | None = None,
        stage2_texture_weight: float | None = None,
        stage2_color_weight: float | None = None,
    ) -> PipelineConfig:
        return replace(
            self.config,
            texture_scan_weight=self.config.texture_scan_weight if texture_scan_weight is None else texture_scan_weight,
            texture_realshot_weight=self.config.texture_realshot_weight
            if texture_realshot_weight is None
            else texture_realshot_weight,
            color_scan_weight=self.config.color_scan_weight if color_scan_weight is None else color_scan_weight,
            color_realshot_weight=self.config.color_realshot_weight if color_realshot_weight is None else color_realshot_weight,
            stage2_texture_weight=self.config.stage2_texture_weight
            if stage2_texture_weight is None
            else stage2_texture_weight,
            stage2_color_weight=self.config.stage2_color_weight if stage2_color_weight is None else stage2_color_weight,
        )

    def score_query_features(
        self,
        working_image: Image.Image,
        query_vit: torch.Tensor,
        query_conv: torch.Tensor,
        score_config: PipelineConfig,
        top_k: int = 10,
        texture_top_families: Optional[int] = None,
        category: str = "",
        use_color: bool = True,
        use_metric_head: bool = True,
        crop_mode: str = "none",
        multiscale_query: bool = False,
        allowed_ids: set[str] | None = None,
    ) -> dict:
        pattern_scores = self.metric_pattern_scores(query_vit, query_conv, score_config) if use_metric_head else []
        texture_stage = "metric_head" if pattern_scores else "dual_dino_cosine"
        if not pattern_scores:
            source_results = {}
            for source, banks in self.source_banks.items():
                source_results[source] = fused_pattern_scores(
                    query_vit=query_vit,
                    query_conv=query_conv,
                    vit_bank=banks["vit"],
                    conv_bank=banks["conv"],
                    config=score_config,
                    manifest=self.manifest,
                )
            pattern_scores = combine_texture_source_scores(
                source_results,
                score_config.texture_source_weights(),
                self.manifest,
            )
        pattern_scores = restrict_to_ids(pattern_scores, allowed_ids)
        pattern_scores = apply_category_filter(pattern_scores, category)
        if not pattern_scores:
            return {
                "error": "no_candidate",
                "detail": "No candidate remained after feature/category filtering.",
                "top_results": [],
                "all_top_results": [],
                "cropped_image_base64": image_to_base64(working_image),
            }

        family_limit = texture_top_families or self.config.texture_top_families
        family_candidates = top_texture_families(pattern_scores, family_limit)
        if use_color:
            query_color = color_descriptor(working_image)
            all_results = rerank_variants_with_color(
                pattern_scores=pattern_scores,
                family_candidates=family_candidates,
                query_descriptor=query_color,
                color_descriptors_by_source=self.color_descriptors_by_source,
                config=score_config,
            )
        else:
            candidate_families = {item["family_id"] for item in family_candidates}
            all_results = [item for item in pattern_scores if item["family_id"] in candidate_families]
            for item in all_results:
                item["confidence"] = item["texture_score"]
                item["score_type"] = "texture_only_cosine_not_probability"
                item["color_score"] = None

        all_results = attach_pattern_info_safe(all_results[: max(top_k, 10)])
        visible = [item for item in all_results if float(item.get("confidence") or 0.0) >= self.config.display_threshold]
        best = all_results[0] if all_results else None
        response = {
            "pattern_id": best.get("pattern_id") if best else None,
            "confidence": float(best.get("confidence")) if best else 0.0,
            "texture_first_families": family_candidates,
            "top_results": visible[:top_k],
            "all_top_results": all_results[:top_k],
            "threshold": self.config.display_threshold,
            "score_type": "two_stage_family_texture_plus_dino_variant_not_probability"
            if use_color
            else "texture_only_cosine_not_probability",
            "texture_stage": texture_stage,
            "source_weights": {
                "texture": score_config.texture_source_weights(),
                "stage2_variant": score_config.stage2_variant_source_weights(),
                "descriptor_color": score_config.color_source_weights(),
                "stage2": score_config.stage2_score_weights(),
            },
            "cropped_image_base64": image_to_base64(working_image),
            "crop_mode": crop_mode,
            "query_multiscale": multiscale_query,
        }
        if not visible:
            response["error"] = "threshold_not_met"
            response["detail"] = "Texture/color candidate exists, but no result passed display threshold."
        return response

    def recognize_many(self, requests: List[dict]) -> List[dict]:
        if not any(banks["vit"] or banks["conv"] for banks in self.source_banks.values()):
            raise RuntimeError(f"No texture feature bank found under {self.config.output_root}")

        prepared = []
        all_views: List[Image.Image] = []
        for item in requests:
            score_config = self.build_score_config(
                texture_scan_weight=item.get("texture_scan_weight"),
                texture_realshot_weight=item.get("texture_realshot_weight"),
                color_scan_weight=item.get("color_scan_weight"),
                color_realshot_weight=item.get("color_realshot_weight"),
                stage2_texture_weight=item.get("stage2_texture_weight"),
                stage2_color_weight=item.get("stage2_color_weight"),
            )
            image = item["image"]
            crop_mode = item.get("crop_mode", "none")
            multiscale_query = bool(item.get("multiscale_query", False))
            working_image = safe_foreground_crop(image) if crop_mode == "foreground" else image
            views = query_texture_views(working_image, multiscale=multiscale_query)
            start = len(all_views)
            all_views.extend(views)
            prepared.append(
                {
                    **item,
                    "score_config": score_config,
                    "working_image": working_image,
                    "view_start": start,
                    "view_count": len(views),
                }
            )

        query_vit_all, query_conv_all = self.extractor.extract_dual(all_views)
        results = []
        for item in prepared:
            start = item["view_start"]
            end = start + item["view_count"]
            results.append(
                self.score_query_features(
                    working_image=item["working_image"],
                    query_vit=query_vit_all[start:end],
                    query_conv=query_conv_all[start:end],
                    score_config=item["score_config"],
                    top_k=item.get("top_k", 10),
                    texture_top_families=item.get("texture_top_families"),
                    category=item.get("category", ""),
                    use_color=bool(item.get("use_color", True)),
                    use_metric_head=bool(item.get("use_metric_head", True)),
                    crop_mode=item.get("crop_mode", "none"),
                    multiscale_query=bool(item.get("multiscale_query", False)),
                    allowed_ids=item.get("allowed_ids"),
                )
            )
        return results

    def recognize(
        self,
        image: Image.Image,
        top_k: int = 10,
        texture_top_families: Optional[int] = None,
        category: str = "",
        use_color: bool = True,
        use_metric_head: bool = True,
        texture_scan_weight: float | None = None,
        texture_realshot_weight: float | None = None,
        color_scan_weight: float | None = None,
        color_realshot_weight: float | None = None,
        stage2_texture_weight: float | None = None,
        stage2_color_weight: float | None = None,
        crop_mode: str = "none",
        multiscale_query: bool = False,
        allowed_ids: set[str] | None = None,
    ) -> dict:
        return self.recognize_many(
            [
                {
                    "image": image,
                    "top_k": top_k,
                    "texture_top_families": texture_top_families,
                    "category": category,
                    "use_color": use_color,
                    "use_metric_head": use_metric_head,
                    "texture_scan_weight": texture_scan_weight,
                    "texture_realshot_weight": texture_realshot_weight,
                    "color_scan_weight": color_scan_weight,
                    "color_realshot_weight": color_realshot_weight,
                    "stage2_texture_weight": stage2_texture_weight,
                    "stage2_color_weight": stage2_color_weight,
                    "crop_mode": crop_mode,
                    "multiscale_query": multiscale_query,
                    "allowed_ids": allowed_ids,
                }
            ]
        )[0]


def apply_category_filter(results: List[dict], category: str) -> List[dict]:
    try:
        from xiaote_platform import filter_pattern_results, normalize_category_filter

        normalized = normalize_category_filter(category)
        if not normalized:
            return results
        return filter_pattern_results(results, normalized)
    except Exception:
        return results


def attach_pattern_info_safe(results: List[dict]) -> List[dict]:
    try:
        from xiaote_platform import attach_pattern_info

        return attach_pattern_info(results)
    except Exception:
        return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Recognize one uploaded image with texture-first/color-second search.")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--feature-root", type=Path, default=None)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--texture-top-families", type=int, default=None)
    parser.add_argument("--category", default="")
    parser.add_argument("--no-color", action="store_true")
    parser.add_argument("--no-metric-head", action="store_true")
    parser.add_argument("--texture-scan-weight", type=float, default=None)
    parser.add_argument("--texture-realshot-weight", type=float, default=None)
    parser.add_argument("--color-scan-weight", type=float, default=None)
    parser.add_argument("--color-realshot-weight", type=float, default=None)
    parser.add_argument("--stage2-texture-weight", type=float, default=None)
    parser.add_argument("--stage2-color-weight", type=float, default=None)
    parser.add_argument("--crop-mode", choices=["none", "foreground"], default="none")
    parser.add_argument("--multiscale-query", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = PipelineConfig(output_root=args.feature_root.resolve() if args.feature_root else PipelineConfig().output_root)
    recognizer = TextureColorRecognizer(config)
    image = load_rgb_image(args.image)
    result = recognizer.recognize(
        image=image,
        top_k=args.top_k,
        texture_top_families=args.texture_top_families,
        category=args.category,
        use_color=not args.no_color,
        use_metric_head=not args.no_metric_head,
        texture_scan_weight=args.texture_scan_weight,
        texture_realshot_weight=args.texture_realshot_weight,
        color_scan_weight=args.color_scan_weight,
        color_realshot_weight=args.color_realshot_weight,
        stage2_texture_weight=args.stage2_texture_weight,
        stage2_color_weight=args.stage2_color_weight,
        crop_mode=args.crop_mode,
        multiscale_query=args.multiscale_query,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
