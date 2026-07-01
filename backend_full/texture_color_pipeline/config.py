from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple


BASE_DIR = Path(__file__).resolve().parents[1]
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
FULL_PATTERN_RE = re.compile(r"^\d{2}-(\d{5})-\d{3}$")
SOURCE_SCAN = "scan"
SOURCE_REALSHOT = "realshot"
SOURCE_NAMES: Tuple[str, str] = (SOURCE_SCAN, SOURCE_REALSHOT)


def env_path(name: str, default: Path) -> Path:
    value = os.getenv(name)
    return Path(value).expanduser().resolve() if value else default.resolve()


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def default_scan_root() -> Path:
    explicit = os.getenv("XIAOTE_SCAN_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    structured = BASE_DIR / "data" / "training_sources" / SOURCE_SCAN
    if structured.exists():
        return structured.resolve()
    return (BASE_DIR / "data" / "reference_data").resolve()


def pattern_family_id(pattern_id: str) -> str:
    """Return the texture family id used before color-level reranking."""
    match = FULL_PATTERN_RE.match(pattern_id or "")
    if match:
        return match.group(1)
    parts = (pattern_id or "").split("-")
    return parts[1] if len(parts) >= 3 else (pattern_id or "")


@dataclass(frozen=True)
class PipelineConfig:
    base_dir: Path = BASE_DIR
    scan_root: Path = default_scan_root()
    realshot_root: Path = env_path("XIAOTE_REALSHOT_ROOT", BASE_DIR / "data" / "training_sources" / SOURCE_REALSHOT)
    decor_root: Path = env_path("XIAOTE_DECOR_ROOT", BASE_DIR / "data" / "decor_info")
    output_root: Path = env_path("XIAOTE_TEXTURE_COLOR_ROOT", BASE_DIR / "data" / "texture_color_features")
    model_vit: Path = env_path("XIAOTE_MODEL_VIT", BASE_DIR / "models" / "dinov3-vith16plus")
    model_conv: Path = env_path("XIAOTE_MODEL_CONV", BASE_DIR / "models" / "dinov3-convnext-large")

    # The old gallery uses 8 rotations x 44 crops = 352 templates per source photo.
    # Keeping this value lets scoring aggregate each original image fairly.
    templates_per_image: int = 352

    # Local top-k inside one original reference image. Larger values are smoother;
    # smaller values are more sensitive to one very similar texture patch.
    local_top_k: int = 5

    # First stage: keep only these texture families before color comparison.
    texture_top_families: int = int(os.getenv("XIAOTE_TEXTURE_TOP_FAMILIES", "200"))

    # Stage 1 source weights. They are used only for texture-family retrieval.
    texture_scan_weight: float = float(os.getenv("XIAOTE_TEXTURE_SCAN_WEIGHT", "0.85"))
    texture_realshot_weight: float = float(os.getenv("XIAOTE_TEXTURE_REALSHOT_WEIGHT", "0.15"))

    # Stage 2 variant source weights. They are used only inside the selected
    # texture families. The scan/realshot values now fuse DINOv3 variant
    # similarities first; color descriptors are kept as diagnostics/fallback.
    color_scan_weight: float = float(os.getenv("XIAOTE_COLOR_SCAN_WEIGHT", "0.25"))
    color_realshot_weight: float = float(os.getenv("XIAOTE_COLOR_REALSHOT_WEIGHT", "0.75"))

    # Stage 2 final score weights. Texture uses the family-level texture score;
    # color uses the available scan/realshot weighted DINOv3 variant score below.
    stage2_texture_weight: float = float(os.getenv("XIAOTE_STAGE2_TEXTURE_WEIGHT", "0.3"))
    stage2_color_weight: float = float(os.getenv("XIAOTE_STAGE2_COLOR_WEIGHT", "0.7"))

    # Stage 2 DINO variant feature preprocessing. Query photos are treated as
    # realshot-like images. When no dedicated stage2 feature bank exists, the
    # recognizer falls back to the regular texture feature scores.
    stage2_realshot_white_balance: bool = env_bool("XIAOTE_STAGE2_REALSHOT_WHITE_BALANCE", True)
    stage2_realshot_color_normalize: bool = env_bool("XIAOTE_STAGE2_REALSHOT_COLOR_NORMALIZE", False)
    stage2_realshot_sample_mode: str = os.getenv("XIAOTE_STAGE2_REALSHOT_SAMPLE_MODE", "center").strip().lower()

    # Color score temperature. Smaller values make color differences matter more.
    color_temperature: float = 0.45

    # Display threshold is still a cosine-derived retrieval score, not a probability.
    display_threshold: float = float(os.getenv("XIAOTE_TEXTURE_COLOR_DISPLAY_THRESHOLD", "0.55"))

    batch_size: int = int(os.getenv("XIAOTE_DINO_BATCH_SIZE", "8"))

    def texture_source_weights(self) -> Dict[str, float]:
        return {
            SOURCE_SCAN: self.texture_scan_weight,
            SOURCE_REALSHOT: self.texture_realshot_weight,
        }

    def color_source_weights(self) -> Dict[str, float]:
        return {
            SOURCE_SCAN: self.color_scan_weight,
            SOURCE_REALSHOT: self.color_realshot_weight,
        }

    def stage2_variant_source_weights(self) -> Dict[str, float]:
        return self.color_source_weights()

    def stage2_score_weights(self) -> Dict[str, float]:
        return {
            "texture": self.stage2_texture_weight,
            "color": self.stage2_color_weight,
        }

    def source_root(self, source: str) -> Path:
        if source == SOURCE_SCAN:
            return self.scan_root
        if source == SOURCE_REALSHOT:
            return self.realshot_root
        raise ValueError(f"Unknown source: {source}")

    def source_vit_feature_dir(self, source: str) -> Path:
        return self.output_root / "texture_features" / source / "dinov3_vith16plus"

    def source_conv_feature_dir(self, source: str) -> Path:
        return self.output_root / "texture_features" / source / "dinov3_convnext_large"

    def source_stage2_vit_feature_dir(self, source: str) -> Path:
        return self.output_root / "stage2_variant_features" / source / "dinov3_vith16plus"

    def source_stage2_conv_feature_dir(self, source: str) -> Path:
        return self.output_root / "stage2_variant_features" / source / "dinov3_convnext_large"

    def source_color_descriptor_dir(self, source: str) -> Path:
        return self.output_root / "color_descriptors" / source

    @property
    def legacy_vit_feature_dir(self) -> Path:
        return self.output_root / "texture_features" / "dinov3_vith16plus"

    @property
    def legacy_conv_feature_dir(self) -> Path:
        return self.output_root / "texture_features" / "dinov3_convnext_large"

    @property
    def legacy_color_descriptor_dir(self) -> Path:
        return self.output_root / "color_descriptors"

    @property
    def vit_feature_dir(self) -> Path:
        return self.source_vit_feature_dir(SOURCE_SCAN)

    @property
    def conv_feature_dir(self) -> Path:
        return self.source_conv_feature_dir(SOURCE_SCAN)

    @property
    def color_descriptor_dir(self) -> Path:
        return self.source_color_descriptor_dir(SOURCE_SCAN)

    @property
    def manifest_path(self) -> Path:
        return self.output_root / "texture_color_manifest.json"

    @property
    def metric_head_path(self) -> Path:
        return self.output_root / "metric_head.pt"


def make_config(output_root: str | None = None) -> PipelineConfig:
    config = PipelineConfig()
    if output_root:
        return PipelineConfig(output_root=Path(output_root).expanduser().resolve())
    return config
