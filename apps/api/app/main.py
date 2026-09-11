"""FastAPI application entrypoint — wires together core services and domain routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.errors import CloudFrontSafeStatusMiddleware, register_exception_handlers
from app.core.rate_limit import limiter
from app.core.realtime_router import router as realtime_router
from app.domains.court.router import router as court_router
from app.domains.friend.router import router as friend_router
from app.domains.group.router import join_router
from app.domains.group.router import router as group_router
from app.domains.group_invite.router import invite_router as group_invite_invite_router
from app.domains.group_invite.router import router as group_invite_router
from app.domains.member.router import router as member_router
from app.domains.notification.router import router as notification_router
from app.domains.schedule.router import router as schedule_router
from app.scheduler.auto_disband import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    yield
    stop_scheduler()


_BASE_DESCRIPTION = (
    "Every error response has the shape `{\"error_code\": string, \"detail\": object}` "
    "— `error_code` is authoritative; clients MUST branch on it, never on the raw "
    "HTTP status code."
)
_CLOUDFRONT_REMAP_NOTE = (
    "\n\n**This environment remaps 403/404 responses to 400** "
    "(`REMAP_403_404_FOR_CLOUDFRONT=true`): production's CloudFront distribution "
    "has a distribution-wide custom error response (403/404 → the SPA's "
    "`/index.html`, needed so a direct browser hit on an Angular client-side route "
    "doesn't 403 from the S3 origin) that would otherwise also swallow these two "
    "status codes' real JSON bodies from this API. A route documented below as "
    "returning 403 or 404 actually returns HTTP 400 here, with the same "
    "`error_code` — see `CloudFrontSafeStatusMiddleware` (app/core/errors.py)."
)


def create_app() -> FastAPI:
    settings = get_settings()
    description = _BASE_DESCRIPTION + (
        _CLOUDFRONT_REMAP_NOTE if settings.remap_403_404_for_cloudfront else ""
    )
    app = FastAPI(title="Rally Stats API", description=description, lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: _rate_limit_exceeded_handler(
            request, cast(RateLimitExceeded, exc)
        ),
    )
    register_exception_handlers(app)

    if settings.remap_403_404_for_cloudfront:
        app.add_middleware(CloudFrontSafeStatusMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_allowed_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(group_router)
    app.include_router(join_router)
    app.include_router(court_router)
    app.include_router(schedule_router)
    app.include_router(member_router)
    app.include_router(friend_router)
    app.include_router(notification_router)
    app.include_router(group_invite_router)
    app.include_router(group_invite_invite_router)
    app.include_router(realtime_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
