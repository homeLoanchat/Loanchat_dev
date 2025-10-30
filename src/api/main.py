"""FastAPI 엔트리 포인트."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from os import getenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.admin import router as admin_router
from src.api.routers.chat import router as chat_router
from src.core.exceptions import register_exception_handlers
from src.core.logging import configure_logging


def _get_allowed_origins() -> list[str]:
    """환경변수 기반 허용 origin 리스트 반환."""

    raw = getenv("LOANBOT_ALLOWED_ORIGINS")
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 기동/종료 시 리소스 초기화 및 정리를 담당."""

    configure_logging()
    register_exception_handlers(app)
    yield


app = FastAPI(title="LoanBot API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(admin_router)
