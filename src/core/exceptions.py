"""도메인 예외 및 FastAPI 에러 핸들러."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from src.core.responses import fail


logger = logging.getLogger(__name__)

INVALID_VALUE = "INVALID_VALUE"
INVALID_RANGE = "INVALID_RANGE"
TIMEOUT = "TIMEOUT"


class LoanBotError(Exception):
    """LoanBot 공통 예외 베이스 클래스."""

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.field = field
        self.details = details


class InvalidValueError(LoanBotError):
    """유효하지 않은 입력값."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=INVALID_VALUE,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            field=field,
            details=details,
        )


class InvalidRangeError(LoanBotError):
    """허용 범위를 벗어난 입력값."""

    def __init__(
        self,
        message: str,
        *,
        field: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=INVALID_RANGE,
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            field=field,
            details=details,
        )


class TimeoutError(LoanBotError):
    """응답 지연."""

    def __init__(
        self,
        message: str = "요청이 제한 시간을 초과했습니다.",
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(
            code=TIMEOUT,
            message=message,
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """FastAPI 앱에 기본 예외 핸들러를 등록한다."""

    @app.exception_handler(LoanBotError)
    async def handle_loanbot_error(
        request: Request, exc: LoanBotError
    ) -> JSONResponse:
        logger.warning(
            "LoanBotError handled",
            extra={"path": request.url.path, "code": exc.code},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=fail(
                code=exc.code,
                message=exc.message,
                field=exc.field,
                details=exc.details,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.debug(
            "Request validation failed",
            extra={"path": request.url.path, "errors": exc.errors()},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=fail(
                code=INVALID_VALUE,
                message="요청 파라미터가 유효하지 않습니다.",
                details={"errors": exc.errors()},
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(
        request: Request, exc: Exception
    ) -> JSONResponse:
        logger.exception("Unexpected error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=fail(
                code="INTERNAL_ERROR",
                message="서버 내부 오류가 발생했습니다.",
            ),
        )


__all__ = [
    "INVALID_RANGE",
    "INVALID_VALUE",
    "TIMEOUT",
    "InvalidRangeError",
    "InvalidValueError",
    "LoanBotError",
    "TimeoutError",
    "register_exception_handlers",
]
