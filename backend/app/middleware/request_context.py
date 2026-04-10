import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Adds a request id to every response and makes it available via request.state.request_id.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        logger = logging.getLogger("orcafind.request")
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["X-Request-Id"] = request_id
        logger.info(
            "%s %s %s %.1fms",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response
