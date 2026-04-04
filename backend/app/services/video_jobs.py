import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import httpx

from app.services.r2_storage import (
    build_object_key,
    get_bucket_name,
    get_download_url,
    get_key_prefix,
    upload_bytes,
)
from app.services.runway_client import RunwayClient
from app.services.video_transform import lowres_watermark_mp4


@dataclass
class VideoJob:
    id: str
    user_id: str
    youtube_url: str
    duration_seconds: int
    style: str
    platform: str
    captions: bool
    delivery_tier: str = "pro"  # pro | free
    delivery_quality: str = "hd"  # hd | watermarked_lowres
    status: str = "queued"  # queued | running | done | failed
    progress: int = 0
    created_at: float = field(default_factory=lambda: time.time())
    updated_at: float = field(default_factory=lambda: time.time())
    error: Optional[str] = None
    result_url: Optional[str] = None
    storage_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "progress": self.progress,
            "error": self.error,
            "result_url": self.result_url,
            "delivery_tier": self.delivery_tier,
            "quality": self.delivery_quality,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


_JOBS: Dict[str, VideoJob] = {}
_LOCK = asyncio.Lock()


def new_job_id() -> str:
    return uuid.uuid4().hex


async def create_job(
    *,
    user_id: str,
    youtube_url: str,
    duration_seconds: int,
    style: str,
    platform: str,
    captions: bool,
    delivery_tier: str = "pro",
) -> VideoJob:
    normalized_tier = delivery_tier if delivery_tier in {"pro", "free"} else "pro"
    job = VideoJob(
        id=new_job_id(),
        user_id=user_id,
        youtube_url=youtube_url,
        duration_seconds=duration_seconds,
        style=style,
        platform=platform,
        captions=captions,
        delivery_tier=normalized_tier,
        delivery_quality="hd" if normalized_tier == "pro" else "watermarked_lowres",
    )
    async with _LOCK:
        _JOBS[job.id] = job
    return job


async def get_job(job_id: str) -> Optional[VideoJob]:
    async with _LOCK:
        return _JOBS.get(job_id)


async def _update(job_id: str, **changes):
    async with _LOCK:
        job = _JOBS.get(job_id)
        if not job:
            return
        for key, value in changes.items():
            setattr(job, key, value)
        job.updated_at = time.time()


async def run_job(job_id: str):
    job = await get_job(job_id)
    if not job:
        return

    await _update(job_id, status="running", progress=5)

    try:
        runway = RunwayClient.from_env()
        runway_job_id = await runway.create_shorts_job(
            youtube_url=job.youtube_url,
            duration_seconds=job.duration_seconds,
            style=job.style,
            platform=job.platform,
            captions=job.captions,
        )

        await _update(job_id, progress=20)

        # Poll Runway job until complete.
        deadline = time.time() + 60 * 12
        result_url: Optional[str] = None
        while time.time() < deadline:
            payload = await runway.get_job(runway_job_id)
            status = str(payload.get("status", "")).lower()
            result_url = runway.extract_result_url(payload) or result_url

            if status in {"succeeded", "success", "completed", "done"} and result_url:
                break
            if status in {"failed", "error"}:
                raise RuntimeError(payload.get("error") or "Runway job failed")

            await _update(job_id, progress=min(95, (await get_job(job_id)).progress + 5))
            await asyncio.sleep(3.0)

        if not result_url:
            raise RuntimeError("Timed out waiting for Runway video output")

        await _update(job_id, progress=96)

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.get(result_url)
            response.raise_for_status()
            video_bytes = response.content

        if job.delivery_tier == "free":
            # Best-effort: if ffmpeg isn't available, keep original to avoid failing the job.
            try:
                video_bytes = lowres_watermark_mp4(video_bytes)
                await _update(job_id, delivery_quality="watermarked_lowres")
            except Exception:
                await _update(job_id, delivery_quality="hd")
                pass

        bucket = get_bucket_name()
        prefix = get_key_prefix()
        object_key = build_object_key(prefix, job.user_id, job_id, job.delivery_tier, extension="mp4")
        upload_bytes(
            bucket=bucket,
            key=object_key,
            content=video_bytes,
            content_type="video/mp4",
        )

        download_url = get_download_url(bucket=bucket, key=object_key)
        await _update(
            job_id,
            status="done",
            progress=100,
            result_url=download_url,
            storage_key=object_key,
        )
    except Exception as exc:
        await _update(job_id, status="failed", progress=100, error=str(exc))
