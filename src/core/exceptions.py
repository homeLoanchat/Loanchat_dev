"""도메인 예외 및 FastAPI 에러 핸들러."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


class LoanBotError(Exception):
    """LoanBot 공통 예외 베이스 클래스."""


class RetrievalError(LoanBotError):
    """TODO: 검색 실패 시 사용할 예외."""


class CalculationError(LoanBotError):
    """TODO: 계산 실패 시 사용할 예외."""


def _serialize_error(exc: LoanBotError) -> dict[str, Any]:
    """Iteration 0용 단순 에러 직렬화."""

    return {
        "detail": str(exc) or exc.__class__.__name__,
    }


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 기본 예외 핸들러를 등록한다."""

    @app.exception_handler(LoanBotError)
    async def handle_loanbot_error(
        request: Request, exc: LoanBotError
    ) -> JSONResponse:
        logger.warning("LoanBotError handled", extra={"path": request.url.path})
        return JSONResponse(status_code=500, content=_serialize_error(exc))
