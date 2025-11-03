"""FastAPI 엔트리 포인트."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import perf_counter

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from config.settings import get_settings
from src.api.routers.admin import router as admin_router
from src.api.routers.calc import router as calc_router
from src.api.routers.chat import router as chat_router
from src.core.exceptions import register_exception_handlers
from src.core.logging import configure_logging
from src.core.metrics import track_latency


# 서버 기동 시 .env 를 자동 로드해 OS 환경 변수로 노출한다.
load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """앱 기동/종료 시 리소스 초기화 및 정리를 담당."""

    settings = get_settings()
    configure_logging()
    # 루트 로그 레벨은 설정에 따라 조정
    import logging

    logging.getLogger().setLevel(settings.log_level.upper())
    yield


app = FastAPI(title="LoanBot API", version="0.1.0", lifespan=lifespan)

register_exception_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def record_request_metrics(request: Request, call_next):
    start = perf_counter()
    response = await call_next(request)
    duration_ms = (perf_counter() - start) * 1000
    track_latency(request.url.path, value=duration_ms)
    return response


app.include_router(chat_router)
app.include_router(calc_router)
app.include_router(admin_router)
