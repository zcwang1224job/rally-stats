"""FastAPI application entrypoint — wires together core services and domain routers."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.rate_limit import limiter
from app.core.realtime_router import router as realtime_router
from app.domains.court.router import router as court_router
from app.domains.friend.router import router as friend_router
from app.domains.group.router import join_router
from app.domains.group.router import router as group_router
from app.domains.member.router import router as member_router
from app.domains.schedule.router import router as schedule_router
from app.scheduler.auto_disband import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    yield
    stop_scheduler()


def create_app() -> FastAPI:
    app = FastAPI(title="Rally Stats API", lifespan=lifespan)

    app.state.limiter = limiter
    app.add_exception_handler(
        RateLimitExceeded,
        lambda request, exc: _rate_limit_exceeded_handler(
            request, cast(RateLimitExceeded, exc)
        ),
    )
    register_exception_handlers(app)

    settings = get_settings()
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
    app.include_router(realtime_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
