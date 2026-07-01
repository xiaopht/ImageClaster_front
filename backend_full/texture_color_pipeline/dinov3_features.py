from __future__ import annotations

from typing import List, Tuple

import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from .config import PipelineConfig


def pooled_feature(outputs) -> torch.Tensor:
    if getattr(outputs, "pooler_output", None) is not None:
        features = outputs.pooler_output
    else:
        hidden = outputs.last_hidden_state
        if hidden.ndim == 3:
            features = hidden.mean(dim=1)
        elif hidden.ndim == 4:
            features = hidden.mean(dim=(2, 3))
        else:
            raise RuntimeError(f"Unsupported model output shape: {tuple(hidden.shape)}")
    return F.normalize(features, p=2, dim=1)


class DualDinoExtractor:
    """Lazy loader for the same dual-DINO backbone used by the existing backend."""

    def __init__(self, config: PipelineConfig, device: str | None = None) -> None:
        self.config = config
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.processor_vit = None
        self.model_vit = None
        self.processor_conv = None
        self.model_conv = None

    def ensure_loaded(self) -> None:
        if self.model_vit is not None and self.model_conv is not None:
            return
        self.processor_vit = AutoImageProcessor.from_pretrained(str(self.config.model_vit), local_files_only=self.config.model_vit.exists())
        self.model_vit = AutoModel.from_pretrained(str(self.config.model_vit), local_files_only=self.config.model_vit.exists()).to(self.device)
        self.model_vit.eval()
        self.processor_conv = AutoImageProcessor.from_pretrained(str(self.config.model_conv), local_files_only=self.config.model_conv.exists())
        self.model_conv = AutoModel.from_pretrained(str(self.config.model_conv), local_files_only=self.config.model_conv.exists()).to(self.device)
        self.model_conv.eval()

    def encode_batch(self, images: List[Image.Image], processor, model) -> torch.Tensor:
        features = []
        for start in range(0, len(images), self.config.batch_size):
            batch = images[start : start + self.config.batch_size]
            inputs = processor(images=batch, return_tensors="pt").to(self.device)
            with torch.inference_mode():
                outputs = model(**inputs)
                features.append(pooled_feature(outputs).cpu())
            del inputs, outputs
            if self.device.type == "cuda":
                torch.cuda.empty_cache()
        return torch.cat(features, dim=0)

    def extract_dual(self, images: List[Image.Image]) -> Tuple[torch.Tensor, torch.Tensor]:
        self.ensure_loaded()
        vit = self.encode_batch(images, self.processor_vit, self.model_vit)
        conv = self.encode_batch(images, self.processor_conv, self.model_conv)
        return vit, conv

