from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

import torch
import torch.nn.functional as F

from .config import PipelineConfig, SOURCE_NAMES, SOURCE_SCAN, pattern_family_id
from .image_ops import color_similarity


FeatureBank = Dict[str, torch.Tensor]
FEATURE_BANK_DTYPE = os.getenv("XIAOTE_FEATURE_BANK_DTYPE", "float16").strip().lower()


def compact_feature_tensor(tensor: torch.Tensor) -> torch.Tensor:
    normalized = F.normalize(tensor.float(), p=2, dim=1)
    if FEATURE_BANK_DTYPE in {"float16", "fp16", "half"}:
        return normalized.half()
    if FEATURE_BANK_DTYPE in {"bfloat16", "bf16"}:
        return normalized.bfloat16()
    return normalized


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_feature_dir(directory: Path) -> FeatureBank:
    bank: FeatureBank = {}
    if not directory.exists():
        return bank
    for path in sorted(directory.glob("*.pt")):
        tensor = torch.load(path, map_location="cpu")
        if isinstance(tensor, dict):
            tensor = tensor.get("features")
        if not isinstance(tensor, torch.Tensor):
            raise RuntimeError(f"Feature file is not a tensor: {path}")
        if tensor.ndim != 2:
            raise RuntimeError(f"Feature tensor must be [N, D], got {tuple(tensor.shape)}: {path}")
        bank[path.stem] = compact_feature_tensor(tensor)
    return bank


def load_color_descriptors(directory: Path) -> Dict[str, dict]:
    descriptors: Dict[str, dict] = {}
    if not directory.exists():
        return descriptors
    for path in sorted(directory.glob("*.json")):
        descriptors[path.stem] = load_json(path)
    return descriptors


def load_source_feature_banks(config: PipelineConfig) -> Dict[str, Dict[str, FeatureBank]]:
    banks: Dict[str, Dict[str, FeatureBank]] = {}
    for source in SOURCE_NAMES:
        vit_bank = load_feature_dir(config.source_vit_feature_dir(source))
        conv_bank = load_feature_dir(config.source_conv_feature_dir(source))
        if source == SOURCE_SCAN and not vit_bank and not conv_bank:
            vit_bank = load_feature_dir(config.legacy_vit_feature_dir)
            conv_bank = load_feature_dir(config.legacy_conv_feature_dir)
        banks[source] = {"vit": vit_bank, "conv": conv_bank}
    return banks


def load_source_color_descriptors(config: PipelineConfig) -> Dict[str, Dict[str, dict]]:
    descriptors: Dict[str, Dict[str, dict]] = {}
    for source in SOURCE_NAMES:
        source_descriptors = load_color_descriptors(config.source_color_descriptor_dir(source))
        if source == SOURCE_SCAN and not source_descriptors:
            source_descriptors = load_color_descriptors(config.legacy_color_descriptor_dir)
        descriptors[source] = source_descriptors
    return descriptors


def aggregate_reference_score(
    query_features: torch.Tensor,
    reference_features: torch.Tensor,
    templates_per_image: int,
    local_top_k: int,
) -> float:
    if reference_features.dtype != query_features.dtype:
        reference_features = reference_features.to(dtype=query_features.dtype)
    similarities = torch.mm(query_features, reference_features.T)
    best_query_similarity = torch.max(similarities, dim=0).values
    if templates_per_image > 0 and best_query_similarity.numel() % templates_per_image == 0:
        per_image = best_query_similarity.reshape(-1, templates_per_image)
        k = max(1, min(local_top_k, templates_per_image))
        per_image_scores = torch.topk(per_image, k=k, dim=1).values.mean(dim=1)
        return float(per_image_scores.mean().item())
    k = max(1, min(local_top_k, best_query_similarity.numel()))
    return float(torch.topk(best_query_similarity, k=k).values.mean().item())


def fused_pattern_scores(
    query_vit: torch.Tensor,
    query_conv: torch.Tensor,
    vit_bank: FeatureBank,
    conv_bank: FeatureBank,
    config: PipelineConfig,
    manifest: dict | None = None,
) -> List[dict]:
    class_ids = sorted(set(vit_bank.keys()) | set(conv_bank.keys()))
    classes = (manifest or {}).get("classes", {})
    results: List[dict] = []
    for pattern_id in class_ids:
        total = 0.0
        weight = 0.0
        vit_score = None
        conv_score = None
        if pattern_id in vit_bank:
            vit_score = aggregate_reference_score(
                query_vit,
                vit_bank[pattern_id],
                config.templates_per_image,
                config.local_top_k,
            )
            total += 0.5 * vit_score
            weight += 0.5
        if pattern_id in conv_bank:
            conv_score = aggregate_reference_score(
                query_conv,
                conv_bank[pattern_id],
                config.templates_per_image,
                config.local_top_k,
            )
            total += 0.5 * conv_score
            weight += 0.5
        if weight == 0:
            continue
        family_id = classes.get(pattern_id, {}).get("family_id") or pattern_family_id(pattern_id)
        results.append(
            {
                "pattern_id": pattern_id,
                "family_id": family_id,
                "texture_score": float(total / weight),
                "vit_score": vit_score,
                "convnext_score": conv_score,
                "available_models": int(vit_score is not None) + int(conv_score is not None),
            }
        )
    results.sort(key=lambda item: item["texture_score"], reverse=True)
    return results


def weighted_available_average(source_scores: Mapping[str, float | None], source_weights: Mapping[str, float]) -> float | None:
    total = 0.0
    total_weight = 0.0
    for source, score in source_scores.items():
        if score is None:
            continue
        weight = max(0.0, float(source_weights.get(source, 0.0)))
        if weight <= 0:
            continue
        total += weight * float(score)
        total_weight += weight
    if total_weight <= 0:
        return None
    return total / total_weight


def combine_texture_source_scores(
    source_results: Mapping[str, List[dict]],
    source_weights: Mapping[str, float],
    manifest: dict | None = None,
) -> List[dict]:
    classes = (manifest or {}).get("classes", {})
    merged: Dict[str, dict] = {}
    for source, results in source_results.items():
        for item in results:
            pattern_id = item["pattern_id"]
            family_id = classes.get(pattern_id, {}).get("family_id") or item.get("family_id") or pattern_family_id(pattern_id)
            target = merged.setdefault(
                pattern_id,
                {
                    "pattern_id": pattern_id,
                    "family_id": family_id,
                    "source_texture_scores": {},
                    "source_model_scores": {},
                },
            )
            target["source_texture_scores"][source] = float(item["texture_score"])
            target["source_model_scores"][source] = {
                "vit_score": item.get("vit_score"),
                "convnext_score": item.get("convnext_score"),
                "metric_score": item.get("metric_score"),
            }

    combined = []
    for item in merged.values():
        score = weighted_available_average(item["source_texture_scores"], source_weights)
        if score is None:
            continue
        item["texture_score"] = float(score)
        item["texture_score_scan"] = item["source_texture_scores"].get("scan")
        item["texture_score_realshot"] = item["source_texture_scores"].get("realshot")
        item["available_texture_sources"] = sorted(item["source_texture_scores"].keys())
        combined.append(item)
    combined.sort(key=lambda value: value["texture_score"], reverse=True)
    return combined


def top_texture_families(pattern_scores: Iterable[dict], limit: int) -> List[dict]:
    families: Dict[str, dict] = {}
    for item in sorted(pattern_scores, key=lambda value: (value.get("family_id") or "", value.get("pattern_id") or "")):
        family_id = item["family_id"]
        if family_id not in families:
            families[family_id] = {
                "family_id": family_id,
                "texture_score": item["texture_score"],
                "best_pattern_id": item["pattern_id"],
                "texture_representative_policy": "first_pattern_in_family",
            }
    ranked = sorted(families.values(), key=lambda item: item["texture_score"], reverse=True)
    return ranked[: max(1, limit)]


def minmax_texture_score(value: float, values: List[float]) -> float:
    if not values:
        return 0.0
    lo = min(values)
    hi = max(values)
    if abs(hi - lo) < 1e-6:
        return 1.0
    return (value - lo) / (hi - lo)


def weighted_stage2_score(texture_score: float, color_score: float, config: PipelineConfig) -> float:
    texture_weight = max(0.0, float(config.stage2_texture_weight))
    color_weight = max(0.0, float(config.stage2_color_weight))
    total_weight = texture_weight + color_weight
    if total_weight <= 0:
        return float(texture_score)
    return float((texture_weight * texture_score + color_weight * color_score) / total_weight)


def rerank_variants_with_color(
    pattern_scores: List[dict],
    family_candidates: List[dict],
    query_descriptor: dict,
    color_descriptors_by_source: Mapping[str, Dict[str, dict]],
    config: PipelineConfig,
) -> List[dict]:
    allowed_families = {item["family_id"] for item in family_candidates}
    family_texture_scores = {item["family_id"]: float(item["texture_score"]) for item in family_candidates}
    candidates = [item for item in pattern_scores if item["family_id"] in allowed_families]
    reranked: List[dict] = []
    for item in candidates:
        source_color_scores: Dict[str, float] = {}
        for source, descriptors in color_descriptors_by_source.items():
            descriptor = descriptors.get(item["pattern_id"])
            if descriptor:
                source_color_scores[source] = color_similarity(query_descriptor, descriptor, config.color_temperature)
        color_score = weighted_available_average(source_color_scores, config.color_source_weights())
        if color_score is None:
            color_score = 0.0
        family_texture_score = family_texture_scores.get(item["family_id"], item["texture_score"])
        confidence = weighted_stage2_score(family_texture_score, color_score, config)
        merged = dict(item)
        merged.update(
            {
                "color_score": float(color_score),
                "confidence": float(confidence),
                "score_type": "two_stage_family_texture_plus_color_not_probability",
                "source_color_scores": source_color_scores,
                "color_score_scan": source_color_scores.get("scan"),
                "color_score_realshot": source_color_scores.get("realshot"),
                "family_texture_score": family_texture_score,
                "stage2_score_weights": config.stage2_score_weights(),
            }
        )
        reranked.append(merged)
    reranked.sort(
        key=lambda item: (
            float(item.get("confidence") or 0.0),
            float(item.get("family_texture_score") or 0.0),
            float(item.get("color_score") or 0.0),
        ),
        reverse=True,
    )
    return reranked


def restrict_to_ids(results: List[dict], allowed_ids: set[str] | None) -> List[dict]:
    if not allowed_ids:
        return results
    return [item for item in results if item.get("pattern_id") in allowed_ids]
