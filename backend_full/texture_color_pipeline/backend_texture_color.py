from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from texture_color_pipeline.config import PipelineConfig
from texture_color_pipeline.recognize_texture_color import TextureColorRecognizer

try:
    from xiaote_platform import (
        favorite_ids_for_user,
        get_user_from_request,
        init_platform,
        record_recognition_result,
        router as platform_router,
        save_uploaded_image,
    )
except Exception:  # pragma: no cover - lets the recognition API run without platform extras.
    favorite_ids_for_user = None
    get_user_from_request = None
    init_platform = None
    record_recognition_result = None
    platform_router = None
    save_uploaded_image = None


app = FastAPI(title="Schattdecor Texture-Color Recognition API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if platform_router is not None:
    app.include_router(platform_router)
admin_web_dir = BASE_DIR / "admin_web"
font_dir = BASE_DIR / "assets" / "fonts"
if font_dir.is_dir():
    app.mount("/fonts", StaticFiles(directory=font_dir), name="fonts")
if admin_web_dir.is_dir():
    app.mount("/admin", StaticFiles(directory=admin_web_dir, html=True), name="admin-web")

config = PipelineConfig()
recognizer: Optional[TextureColorRecognizer] = None


def get_recognizer() -> TextureColorRecognizer:
    global recognizer
    if recognizer is None:
        recognizer = TextureColorRecognizer(config)
    return recognizer


@app.on_event("startup")
def startup() -> None:
    if init_platform is not None:
        init_platform()
    get_recognizer()


@app.get("/")
def root() -> dict:
    return {
        "message": "Texture-first/color-second recognition API is running.",
        "feature_root": str(config.output_root),
        "recognizer": get_recognizer().ready_status(),
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, **get_recognizer().ready_status()}


@app.post("/recognize-texture-color")
async def recognize_texture_color(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(""),
    top_k: int = Form(10),
    texture_top_families: int = Form(0),
    use_color: bool = Form(True),
    use_metric_head: bool = Form(True),
    texture_scan_weight: Optional[float] = Form(None),
    texture_realshot_weight: Optional[float] = Form(None),
    color_scan_weight: Optional[float] = Form(None),
    color_realshot_weight: Optional[float] = Form(None),
    stage2_texture_weight: Optional[float] = Form(None),
    stage2_color_weight: Optional[float] = Form(None),
    crop_mode: str = Form("none"),
    multiscale_query: bool = Form(False),
) -> dict:
    file_bytes = await file.read()
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(file_bytes))).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}")
    if crop_mode not in {"none", "foreground"}:
        raise HTTPException(status_code=400, detail="crop_mode must be 'none' or 'foreground'")

    saved_path = None
    if save_uploaded_image is not None:
        saved_path = save_uploaded_image(file_bytes, file.filename)

    try:
        result = get_recognizer().recognize(
            image=image,
            top_k=max(1, min(int(top_k), 30)),
            texture_top_families=int(texture_top_families) if texture_top_families else None,
            category=category,
            use_color=bool(use_color),
            use_metric_head=bool(use_metric_head),
            texture_scan_weight=texture_scan_weight,
            texture_realshot_weight=texture_realshot_weight,
            color_scan_weight=color_scan_weight,
            color_realshot_weight=color_realshot_weight,
            stage2_texture_weight=stage2_texture_weight,
            stage2_color_weight=stage2_color_weight,
            crop_mode=crop_mode,
            multiscale_query=bool(multiscale_query),
        )
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Recognition failed: {exc}")

    if get_user_from_request is not None and favorite_ids_for_user is not None:
        user = get_user_from_request(request)
        if user:
            favorite_ids = favorite_ids_for_user(user["id"])
            for key in ("top_results", "all_top_results"):
                for item in result.get(key, []):
                    item["favorited"] = item.get("pattern_id") in favorite_ids

    if record_recognition_result is not None:
        recognition_id = record_recognition_result(
            request=request,
            image_path=saved_path,
            all_top_results=result.get("all_top_results", []),
            visible_results=result.get("top_results", []),
            status="matched" if not result.get("error") else result.get("error"),
            reason=result.get("detail", "ok"),
            category=category or None,
            threshold=result.get("threshold"),
        )
        result["recognition_id"] = recognition_id
    return result
