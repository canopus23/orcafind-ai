import os
from typing import Any, Dict, Optional

import httpx


class RunwayClient:
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def from_env() -> "RunwayClient":
        api_key = os.getenv("RUNWAY_API_KEY")
        base_url = os.getenv("RUNWAY_API_BASE_URL", "").strip() or "https://api.runwayml.com"
        if not api_key:
            raise RuntimeError("Missing required env var: RUNWAY_API_KEY")
        return RunwayClient(api_key=api_key, base_url=base_url)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def create_shorts_job(
        self,
        *,
        youtube_url: str,
        duration_seconds: int,
        style: str,
        platform: str,
        captions: bool,
    ) -> str:
        """
        Minimal placeholder integration.
        Set RUNWAY_SHORTS_CREATE_PATH and RUNWAY_JOB_STATUS_PATH if your Runway API differs.
        """
        create_path = os.getenv("RUNWAY_SHORTS_CREATE_PATH", "/v1/shorts")
        payload: Dict[str, Any] = {
            "input": {"youtube_url": youtube_url},
            "duration_seconds": duration_seconds,
            "style": style,
            "platform": platform,
            "captions": captions,
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                f"{self.base_url}{create_path}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        job_id = data.get("id") or data.get("job_id")
        if not job_id:
            raise RuntimeError("Runway response missing job id")
        return str(job_id)

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        status_path = os.getenv("RUNWAY_JOB_STATUS_PATH", "/v1/jobs/{job_id}")
        url = f"{self.base_url}{status_path}".format(job_id=job_id)

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    @staticmethod
    def extract_result_url(job_payload: Dict[str, Any]) -> Optional[str]:
        # Tries a few common shapes; adjust if your provider differs.
        for key in ("output_url", "result_url", "url"):
            value = job_payload.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        output = job_payload.get("output")
        if isinstance(output, dict):
            value = output.get("url") or output.get("video_url")
            if isinstance(value, str) and value.startswith("http"):
                return value
        return None

