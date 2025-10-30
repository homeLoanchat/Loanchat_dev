"""FastAPI 엔트리 포인트."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routers.admin import router as admin_router
from src.api.routers.chat import router as chat_router


def create_app() -> FastAPI:
    """FastAPI 애플리케이션을 구성한다."""

    app = FastAPI(title="LoanBot API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(chat_router)
    app.include_router(admin_router)

    return app


app = create_app()
