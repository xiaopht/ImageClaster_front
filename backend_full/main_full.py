from __future__ import annotations

import io
import os
import time
import queue
import asyncio
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from texture_color_pipeline.config import PipelineConfig
from texture_color_pipeline.recognize_texture_color import TextureColorRecognizer
from xiaote_platform import (
    favorite_ids_for_user,
    get_user_from_request,
    init_platform,
    record_recognition_result,
    router as platform_router,
    save_uploaded_image,
)

BASE_DIR = Path(__file__).resolve().parent
ADMIN_WEB_DIR = BASE_DIR / "admin_web"
FONT_DIR = BASE_DIR / "assets" / "fonts"

app = FastAPI(title="Schattdecor Sense Full Recognition API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(platform_router)

if FONT_DIR.exists():
    app.mount("/fonts", StaticFiles(directory=str(FONT_DIR)), name="fonts")
if ADMIN_WEB_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(ADMIN_WEB_DIR), html=True), name="admin-web")
    app.mount("/admin-web", StaticFiles(directory=str(ADMIN_WEB_DIR), html=True), name="admin-web-legacy")

config = PipelineConfig()
recognizer: Optional[TextureColorRecognizer] = None
GPU_BATCH_SIZE = int(os.getenv("XIAOTE_GPU_BATCH_SIZE", "8"))
GPU_BATCH_WAIT_SECONDS = float(os.getenv("XIAOTE_GPU_BATCH_WAIT_MS", "80")) / 1000.0
GPU_QUEUE_MAXSIZE = int(os.getenv("XIAOTE_GPU_QUEUE_MAXSIZE", "50"))
GPU_JOB_TIMEOUT_SECONDS = float(os.getenv("XIAOTE_GPU_JOB_TIMEOUT_SECONDS", "120"))


@dataclass
class RecognitionJob:
    payload: dict
    loop: asyncio.AbstractEventLoop
    future: asyncio.Future


recognition_queue: "queue.Queue[RecognitionJob]" = queue.Queue(maxsize=GPU_QUEUE_MAXSIZE)
recognition_worker_started = False
recognition_worker_thread: Optional[threading.Thread] = None


def get_recognizer() -> TextureColorRecognizer:
    global recognizer
    if recognizer is None:
        recognizer = TextureColorRecognizer(config)
    return recognizer


def _set_future_result(future: asyncio.Future, result: dict) -> None:
    if not future.done():
        future.set_result(result)


def _set_future_exception(future: asyncio.Future, exc: Exception) -> None:
    if not future.done():
        future.set_exception(exc)


def recognition_batch_size() -> int:
    return max(1, GPU_BATCH_SIZE)


def recognition_queue_status() -> dict:
    return {
        "batch_size": recognition_batch_size(),
        "batch_wait_ms": int(GPU_BATCH_WAIT_SECONDS * 1000),
        "queue_maxsize": GPU_QUEUE_MAXSIZE,
        "queued": recognition_queue.qsize(),
        "job_timeout_seconds": GPU_JOB_TIMEOUT_SECONDS,
        "worker_started": recognition_worker_started,
    }


def recognition_worker() -> None:
    print(
        "[Recognition Queue] worker started: "
        f"batch_size={recognition_batch_size()}, "
        f"wait_ms={GPU_BATCH_WAIT_SECONDS * 1000:.0f}, "
        f"queue_max={GPU_QUEUE_MAXSIZE}"
    )
    while True:
        first_job = recognition_queue.get()
        jobs = [first_job]
        deadline = time.monotonic() + max(0.0, GPU_BATCH_WAIT_SECONDS)

        while len(jobs) < recognition_batch_size():
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                break
            try:
                jobs.append(recognition_queue.get(timeout=timeout))
            except queue.Empty:
                break

        active_jobs = [job for job in jobs if not job.future.cancelled()]
        try:
            if active_jobs:
                payloads = [job.payload for job in active_jobs]
                results = get_recognizer().recognize_many(payloads)
                for job, result in zip(active_jobs, results):
                    job.loop.call_soon_threadsafe(_set_future_result, job.future, result)
        except Exception as exc:
            for job in active_jobs:
                job.loop.call_soon_threadsafe(_set_future_exception, job.future, exc)
        finally:
            for _ in jobs:
                recognition_queue.task_done()


def start_recognition_worker_once() -> None:
    global recognition_worker_started
    global recognition_worker_thread
    if recognition_worker_started:
        return
    recognition_worker_thread = threading.Thread(
        target=recognition_worker,
        name="schatt-ai-recognition-worker",
        daemon=True,
    )
    recognition_worker_thread.start()
    recognition_worker_started = True


async def submit_recognition_job(payload: dict) -> dict:
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    job = RecognitionJob(payload=payload, loop=loop, future=future)
    try:
        recognition_queue.put_nowait(job)
    except queue.Full:
        raise HTTPException(status_code=503, detail="当前识别人数较多，请稍后重试")
    try:
        return await asyncio.wait_for(future, timeout=GPU_JOB_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        future.cancel()
        raise HTTPException(status_code=503, detail="识别排队超时，请稍后重试")


@app.on_event("startup")
def startup() -> None:
    init_platform()
    get_recognizer()
    start_recognition_worker_once()


@app.get("/")
def root() -> dict:
    return {
        "ok": True,
        "service": "schattdecor-sense-full-recognition",
        "feature_root": str(config.output_root),
        "recognizer": get_recognizer().ready_status(),
        "recognition_queue": recognition_queue_status(),
    }


@app.get("/health")
def health() -> dict:
    return {"ok": True, **get_recognizer().ready_status(), "recognition_queue": recognition_queue_status()}


def use_crop_to_crop_mode(use_crop: str | bool | None) -> str:
    text = str(use_crop).strip().lower()
    if text in {"false", "0", "no", "off", "none"}:
        return "none"
    return "foreground"


async def run_recognition(
    request: Request,
    file: UploadFile,
    category: str,
    top_k: int,
    crop_mode: str,
    use_color: bool,
    use_metric_head: bool,
    texture_top_families: int,
    multiscale_query: bool,
    stage2_texture_weight: Optional[float] = None,
    stage2_color_weight: Optional[float] = None,
) -> dict:
    file_bytes = await file.read()
    try:
        image = ImageOps.exif_transpose(Image.open(io.BytesIO(file_bytes))).convert("RGB")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid image upload: {exc}")

    if crop_mode not in {"none", "foreground"}:
        raise HTTPException(status_code=400, detail="crop_mode must be 'none' or 'foreground'")

    saved_path = save_uploaded_image(file_bytes, file.filename)
    try:
        result = await submit_recognition_job(
            {
                "image": image,
                "top_k": max(1, min(int(top_k), 30)),
                "texture_top_families": int(texture_top_families) if texture_top_families else None,
                "category": category or "",
                "use_color": bool(use_color),
                "use_metric_head": bool(use_metric_head),
                "crop_mode": crop_mode,
                "multiscale_query": bool(multiscale_query),
                "stage2_texture_weight": stage2_texture_weight,
                "stage2_color_weight": stage2_color_weight,
            }
        )
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise exc
        raise HTTPException(status_code=503, detail=f"Recognition failed: {exc}")

    user = get_user_from_request(request)
    if user:
        favorite_ids = favorite_ids_for_user(user["id"])
        for key in ("top_results", "all_top_results"):
            for item in result.get(key, []):
                item["favorited"] = item.get("pattern_id") in favorite_ids

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


@app.post("/recognize")
async def recognize_compat(
    request: Request,
    file: UploadFile = File(...),
    use_crop: str = Form("true"),
    category: str = Form(""),
    top_k: int = Form(10),
) -> dict:
    return await run_recognition(
        request=request,
        file=file,
        category=category,
        top_k=top_k,
        crop_mode=use_crop_to_crop_mode(use_crop),
        use_color=True,
        use_metric_head=True,
        texture_top_families=0,
        multiscale_query=False,
    )


@app.post("/recognize-texture-color")
async def recognize_texture_color(
    request: Request,
    file: UploadFile = File(...),
    category: str = Form(""),
    top_k: int = Form(10),
    texture_top_families: int = Form(0),
    use_color: bool = Form(True),
    use_metric_head: bool = Form(True),
    crop_mode: str = Form("none"),
    multiscale_query: bool = Form(False),
    stage2_texture_weight: Optional[float] = Form(None),
    stage2_color_weight: Optional[float] = Form(None),
) -> dict:
    return await run_recognition(
        request=request,
        file=file,
        category=category,
        top_k=top_k,
        crop_mode=crop_mode,
        use_color=use_color,
        use_metric_head=use_metric_head,
        texture_top_families=texture_top_families,
        multiscale_query=multiscale_query,
        stage2_texture_weight=stage2_texture_weight,
        stage2_color_weight=stage2_color_weight,
    )
