"""Semantic error-code response schema (constitution principle VIII: no hardcoded
user-facing strings from the backend — the frontend maps error_code to an i18n key)."""

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


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
