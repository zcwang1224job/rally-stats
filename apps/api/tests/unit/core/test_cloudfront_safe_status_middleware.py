"""CloudFrontSafeStatusMiddleware — production's CloudFront distribution
intercepts 403/404 distribution-wide (SPA-routing custom error pages) and
would otherwise swallow the API's own legitimate 403/404 JSON bodies. Built
against a throwaway FastAPI app (not the real `app.main.app`) so this
doesn't need the DB or touch the cached `get_settings()` singleton the rest
of the suite relies on."""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.errors import ApiError, CloudFrontSafeStatusMiddleware, register_exception_handlers


def _make_app(*, with_middleware: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    if with_middleware:
        app.add_middleware(CloudFrontSafeStatusMiddleware)

    @app.get("/forbidden")
    async def _forbidden() -> None:
        raise ApiError("EMAIL_NOT_VERIFIED", status_code=403)

    @app.get("/missing")
    async def _missing() -> None:
        raise ApiError("GROUP_NOT_FOUND", status_code=404)

    @app.get("/conflict")
    async def _conflict() -> None:
        raise ApiError("ALREADY_VERIFIED", status_code=409)

    return app


async def test_without_middleware_403_passes_through_unchanged() -> None:
    app = _make_app(with_middleware=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/forbidden")
    assert response.status_code == 403
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_with_middleware_403_is_remapped_to_400_but_error_code_unchanged() -> None:
    app = _make_app(with_middleware=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/forbidden")
    assert response.status_code == 400
    assert response.json()["error_code"] == "EMAIL_NOT_VERIFIED"


async def test_with_middleware_404_is_remapped_to_400_but_error_code_unchanged() -> None:
    app = _make_app(with_middleware=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/missing")
    assert response.status_code == 400
    assert response.json()["error_code"] == "GROUP_NOT_FOUND"


async def test_with_middleware_other_status_codes_are_untouched() -> None:
    """409 isn't in CloudFront's error-page list, so it must pass through —
    proves the middleware only touches the two codes CloudFront actually
    intercepts, not every 4xx."""
    app = _make_app(with_middleware=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/conflict")
    assert response.status_code == 409
    assert response.json()["error_code"] == "ALREADY_VERIFIED"
