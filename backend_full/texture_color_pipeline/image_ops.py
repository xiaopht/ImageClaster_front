from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Iterable, List

import numpy as np
from PIL import Image, ImageFilter, ImageOps


TEMPLATE_MAX_SIDE = int(os.getenv("XIAOTE_TEMPLATE_MAX_SIDE", "1600"))
COLOR_MAX_SIDE = int(os.getenv("XIAOTE_COLOR_MAX_SIDE", "1600"))


def load_rgb_image(path: str | Path) -> Image.Image:
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def resize_long_side(image: Image.Image, max_side: int) -> Image.Image:
    if max_side <= 0:
        return image
    width, height = image.size
    current = max(width, height)
    if current <= max_side:
        return image
    scale = max_side / float(current)
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return image.resize(new_size, Image.Resampling.BICUBIC)


def texture_view(image: Image.Image) -> Image.Image:
    """Remove most color information while preserving texture and local contrast."""
    gray = ImageOps.grayscale(image)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageOps.equalize(gray)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.8, percent=145, threshold=2))
    return gray.convert("RGB")


def gray_world_white_balance(image: Image.Image, eps: float = 1e-6) -> Image.Image:
    """Simple illumination normalization before color descriptors are computed."""
    arr = np.asarray(image.convert("RGB"), dtype=np.float32)
    channel_mean = arr.reshape(-1, 3).mean(axis=0)
    target = float(channel_mean.mean())
    scale = target / np.maximum(channel_mean, eps)
    balanced = np.clip(arr * scale.reshape(1, 1, 3), 0, 255).astype(np.uint8)
    return Image.fromarray(balanced, mode="RGB")


def center_crop_ratio(image: Image.Image, ratio: float = 0.92) -> Image.Image:
    ratio = max(0.1, min(1.0, ratio))
    width, height = image.size
    crop_w = int(width * ratio)
    crop_h = int(height * ratio)
    left = (width - crop_w) // 2
    top = (height - crop_h) // 2
    return image.crop((left, top, left + crop_w, top + crop_h))


def color_descriptor(image: Image.Image, bins: int = 16) -> dict:
    """Compute a compact Lab-like color descriptor after white balance."""
    balanced = gray_world_white_balance(center_crop_ratio(resize_long_side(image, COLOR_MAX_SIDE)))
    lab = np.asarray(balanced.convert("LAB"), dtype=np.float32)
    pixels = lab.reshape(-1, 3)
    mean = pixels.mean(axis=0)
    std = pixels.std(axis=0)
    histograms = []
    for channel in range(3):
        hist, _ = np.histogram(pixels[:, channel], bins=bins, range=(0, 255))
        hist = hist.astype(np.float32)
        hist /= max(1.0, float(hist.sum()))
        histograms.append(hist)
    return {
        "space": "PIL_LAB_after_gray_world",
        "bins": bins,
        "mean": mean.tolist(),
        "std": std.tolist(),
        "hist": np.concatenate(histograms).tolist(),
    }


def average_color_descriptors(descriptors: Iterable[dict]) -> dict:
    items = list(descriptors)
    if not items:
        return {}
    mean = np.asarray([item["mean"] for item in items], dtype=np.float32).mean(axis=0)
    std = np.asarray([item["std"] for item in items], dtype=np.float32).mean(axis=0)
    hist = np.asarray([item["hist"] for item in items], dtype=np.float32).mean(axis=0)
    hist /= max(1e-6, float(hist.sum()))
    return {
        "space": items[0].get("space", "PIL_LAB_after_gray_world"),
        "bins": int(items[0].get("bins", 16)),
        "mean": mean.tolist(),
        "std": std.tolist(),
        "hist": hist.tolist(),
        "source_images": len(items),
    }


def color_distance(query: dict, reference: dict) -> float:
    if not query or not reference:
        return 1.0
    q_mean = np.asarray(query["mean"], dtype=np.float32)
    r_mean = np.asarray(reference["mean"], dtype=np.float32)
    q_hist = np.asarray(query["hist"], dtype=np.float32)
    r_hist = np.asarray(reference["hist"], dtype=np.float32)
    mean_distance = float(np.linalg.norm(q_mean - r_mean) / 255.0)
    hist_delta = np.sqrt(np.maximum(q_hist, 0.0)) - np.sqrt(np.maximum(r_hist, 0.0))
    hist_distance = float(np.dot(hist_delta, hist_delta))
    return 0.65 * mean_distance + 0.35 * hist_distance


def color_similarity(query: dict, reference: dict, temperature: float = 0.45) -> float:
    distance = color_distance(query, reference)
    return float(math.exp(-distance / max(1e-6, temperature)))


def build_44_crops(image: Image.Image) -> List[Image.Image]:
    width, height = image.size
    crops: List[Image.Image] = [image]
    step_x, step_y = width // 4, height // 4
    size_x, size_y = width // 2, height // 2
    for x in [0, step_x, step_x * 2]:
        for y in [0, step_y, step_y * 2]:
            crops.append(image.crop((x, y, x + size_x, y + size_y)))
    w3, h3 = width // 3, height // 3
    for i in range(3):
        for j in range(3):
            crops.append(image.crop((i * w3, j * h3, (i + 1) * w3, (j + 1) * h3)))
    w5, h5 = width // 5, height // 5
    for i in range(5):
        for j in range(5):
            crops.append(image.crop((i * w5, j * h5, (i + 1) * w5, (j + 1) * h5)))
    return crops


def largest_valid_rotated_rectangle(width: int, height: int, angle: float) -> tuple[int, int]:
    radians = math.radians(angle % 180)
    sin_angle = abs(math.sin(radians))
    cos_angle = abs(math.cos(radians))
    if sin_angle < 1e-8 or cos_angle < 1e-8:
        return width, height
    width_is_longer = width >= height
    side_long, side_short = (width, height) if width_is_longer else (height, width)
    if height <= 2 * sin_angle * cos_angle * width:
        short_half = side_short / 2
        crop_width = short_half / max(1e-6, sin_angle)
        crop_height = short_half / max(1e-6, cos_angle)
        if not width_is_longer:
            crop_width, crop_height = crop_height, crop_width
    else:
        cos_double = cos_angle * cos_angle - sin_angle * sin_angle
        crop_width = (width * cos_angle - height * sin_angle) / cos_double
        crop_height = (height * cos_angle - width * sin_angle) / cos_double
    return max(1, int(abs(crop_width)) - 2), max(1, int(abs(crop_height)) - 2)


def rotate_without_padding(image: Image.Image, angle: int) -> Image.Image:
    if angle % 360 == 0:
        return image.copy()
    rotated = image.rotate(angle, expand=True, resample=Image.Resampling.BICUBIC, fillcolor=(0, 0, 0))
    crop_width, crop_height = largest_valid_rotated_rectangle(image.width, image.height, angle)
    crop_width = min(crop_width, rotated.width)
    crop_height = min(crop_height, rotated.height)
    left = (rotated.width - crop_width) // 2
    top = (rotated.height - crop_height) // 2
    return rotated.crop((left, top, left + crop_width, top + crop_height))


def reference_texture_templates(image: Image.Image) -> List[Image.Image]:
    texture = texture_view(resize_long_side(image, TEMPLATE_MAX_SIDE))
    templates: List[Image.Image] = []
    for angle in [0, 45, 90, 135, 180, 225, 270, 315]:
        templates.extend(build_44_crops(rotate_without_padding(texture, angle)))
    return templates


def query_texture_views(image: Image.Image, multiscale: bool = False) -> List[Image.Image]:
    texture = texture_view(resize_long_side(image, TEMPLATE_MAX_SIDE))
    if not multiscale:
        return [texture]
    return build_44_crops(texture)
