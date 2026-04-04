import uuid
import time
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.responses import JSONResponse


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Adds a request id to every response and makes it available via request.state.request_id.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        start = time.perf_counter()
        logger = logging.getLogger("orcafind.request")
        try:
            response: Response = await call_next(request)
        except Exception:
            # Ensure we always return a JSON error (and preserve request id),
            # so clients don't misinterpret a plain 500 as a CORS/network issue.
            logger.exception("Unhandled error for %s %s", request.method, request.url.path)
            response = JSONResponse(
                status_code=500,
                content={"detail": "Internal Server Error", "request_id": request_id},
            )
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
