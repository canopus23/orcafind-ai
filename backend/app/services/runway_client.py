import os
import json
from typing import Any, Dict, Optional

import httpx


class RunwayClient:
    def __init__(self, api_key: str, base_url: str, workflow_id: str, version: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.workflow_id = workflow_id
        self.version = version

    @staticmethod
    def from_env() -> "RunwayClient":
        api_key = os.getenv("RUNWAY_API_KEY")
        # Runway docs list the API hostname as `api.dev.runwayml.com`.
        # Users can override this for their environment.
        base_url = os.getenv("RUNWAY_API_BASE_URL", "").strip() or "https://api.dev.runwayml.com"
        workflow_id = (os.getenv("RUNWAY_WORKFLOW_ID", "").strip() or "")
        # Runway requires an explicit API version header.
        version = os.getenv("RUNWAY_VERSION", "").strip() or "2024-11-06"
        if not api_key:
            raise RuntimeError("Missing required env var: RUNWAY_API_KEY")
        if "api.runwayml.com" in base_url:
            raise RuntimeError(
                "Invalid RUNWAY_API_BASE_URL: use https://api.dev.runwayml.com (Runway API host), not api.runwayml.com"
            )
        if not workflow_id:
            raise RuntimeError("Missing required env var: RUNWAY_WORKFLOW_ID")
        # Normalize so callers can set either https://api.dev.runwayml.com or https://api.dev.runwayml.com/v1
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/v1"):
            normalized = f"{normalized}/v1"
        return RunwayClient(api_key=api_key, base_url=normalized, workflow_id=workflow_id, version=version)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": self.version,
        }

    async def _try_request(self, method: str, url: str, *, json_body: Optional[dict] = None) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, url, headers=self._headers(), json=json_body)
            if response.status_code >= 400:
                body_preview = response.text[:800] if response.text else ""
                raise RuntimeError(f"Runway API error {response.status_code} for {url}: {body_preview}")
            try:
                return response.json()
            except json.JSONDecodeError:
                raise RuntimeError(f"Runway API returned non-JSON response for {url}: {response.text[:800]}")

    async def create_shorts_job(
        self,
        *,
        youtube_url: str,
        duration_seconds: int,
        style: str,
        platform: str,
        captions: bool,
    ) -> str:
        # Run the published workflow. Your workflow inputs must match these keys.
        inputs = {
            "youtube_url": youtube_url,
            "duration_seconds": duration_seconds,
            "style": style,
            "platform": platform,
            "captions": captions,
        }

        payload: Dict[str, Any] = {"inputs": inputs}

        # Endpoint names differ across releases; try a few common patterns.
        # Note: Workflows must be published in the developer portal to be callable.
        candidates = [
            f"{self.base_url}/workflows/{self.workflow_id}/invocations",
            f"{self.base_url}/workflows/{self.workflow_id}/runs",
            f"{self.base_url}/workflows/{self.workflow_id}/invoke",
            # Alternate: global workflow invocation endpoint.
            f"{self.base_url}/workflow_invocations",
            f"{self.base_url}/invocations",
        ]

        last_exc: Optional[Exception] = None
        data: Dict[str, Any] = {}
        for url in candidates:
            try:
                # For global endpoints, include workflow id in body.
                json_body = payload
                if url.endswith("/workflow_invocations") or url.endswith("/invocations"):
                    json_body = {
                        "workflow_id": self.workflow_id,
                        "workflowId": self.workflow_id,
                        **payload,
                    }
                data = await self._try_request("POST", url, json_body=json_body)
                break
            except Exception as exc:
                last_exc = exc
                continue

        if not data and last_exc:
            raise RuntimeError(
                f"Failed to start Runway workflow job. "
                f"Check that RUNWAY_WORKFLOW_ID '{self.workflow_id}' is published in the Runway developer portal and your API key has access. "
                f"Last error: {last_exc}"
            )

        job_id = data.get("id") or data.get("invocation_id") or data.get("run_id") or data.get("job_id")
        if not job_id:
            raise RuntimeError("Runway response missing job id")
        return str(job_id)

    async def get_job(self, job_id: str) -> Dict[str, Any]:
        candidates = [
            f"{self.base_url}/workflows/{self.workflow_id}/invocations/{job_id}",
            f"{self.base_url}/workflows/{self.workflow_id}/runs/{job_id}",
            f"{self.base_url}/invocations/{job_id}",
            f"{self.base_url}/workflow_invocations/{job_id}",
            f"{self.base_url}/tasks/{job_id}",
        ]

        last_exc: Optional[Exception] = None
        for url in candidates:
            try:
                return await self._try_request("GET", url)
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise RuntimeError(f"Failed to fetch Runway job status for {job_id}. Last error: {last_exc}")
        raise RuntimeError("Failed to fetch Runway job status")

    @staticmethod
    def extract_result_url(job_payload: Dict[str, Any]) -> Optional[str]:
        # Tries a few common shapes; adjust if Runway changes the payload.
        for key in ("output_url", "result_url", "url"):
            value = job_payload.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        output = job_payload.get("output")
        if isinstance(output, dict):
            value = output.get("url") or output.get("video_url")
            if isinstance(value, str) and value.startswith("http"):
                return value
        if isinstance(output, list):
            for item in output:
                if isinstance(item, str) and item.startswith("http"):
                    return item
                if isinstance(item, dict):
                    value = item.get("url") or item.get("video_url")
                    if isinstance(value, str) and value.startswith("http"):
                        return value
        return None
