"""Semantic error-code response schema (constitution principle VIII: no hardcoded
user-facing strings from the backend — the frontend maps error_code to an i18n key)."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class ApiError(Exception):
    """Raise with a semantic error_code; never a hardcoded human-readable message."""

    def __init__(
        self,
        error_code: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.error_code = error_code
        self.status_code = status_code
        self.detail = detail or {}
        super().__init__(error_code)


def _error_response(
    error_code: str, status_code: int, detail: dict[str, object] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": error_code, "detail": detail or {}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(exc.error_code, exc.status_code, exc.detail)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _error_response(
            "VALIDATION_ERROR",
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            # exc.errors() may embed raw exception objects (e.g. a
            # field_validator's ValueError) in ctx.error, which json.dumps
            # can't serialize directly — jsonable_encoder converts those to
            # strings the same way FastAPI's own default handler does.
            {"errors": jsonable_encoder(exc.errors())},
        )


_CLOUDFRONT_INTERCEPTED_STATUS_CODES = frozenset({403, 404})
_CLOUDFRONT_SAFE_STATUS_CODE = 400


class CloudFrontSafeStatusMiddleware(BaseHTTPMiddleware):
    """Production's CloudFront distribution has custom error responses
    configured distribution-wide (403/404 -> /index.html + 200, needed so a
    direct browser hit on an Angular client-side route doesn't 403 from the
    S3 origin) — CloudFront has no way to scope that to the SPA's own path
    pattern only, so it also intercepts the API origin's legitimate 403/404
    JSON error bodies (e.g. EMAIL_NOT_VERIFIED, GROUP_NOT_FOUND) and
    replaces them with the SPA page, which the frontend then fails to parse
    as JSON and surfaces as a generic UNKNOWN_ERROR.

    Nothing in this codebase branches on the literal HTTP status code
    (constitution VIII — always the `error_code` body field), so remapping
    403/404 to a status CloudFront doesn't intercept is a safe, purely
    transport-level fix — `error_code` in the body is untouched. Gated by
    `settings.remap_403_404_for_cloudfront` (only enabled for the
    production API, which sits behind that distribution)."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if response.status_code in _CLOUDFRONT_INTERCEPTED_STATUS_CODES:
            response.status_code = _CLOUDFRONT_SAFE_STATUS_CODE
        return response
