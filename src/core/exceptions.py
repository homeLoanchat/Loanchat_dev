"""도메인 예외 및 FastAPI 에러 핸들러."""

from __future__ import annotations

from fastapi import FastAPI


class LoanBotError(Exception):
    """LoanBot 공통 예외 베이스 클래스."""


class RetrievalError(LoanBotError):
    """TODO: 검색 실패 시 사용할 예외."""


class CalculationError(LoanBotError):
    """TODO: 계산 실패 시 사용할 예외."""


def register_exception_handlers(app: FastAPI) -> None:
    """TODO: FastAPI 앱에 커스텀 예외 핸들러를 등록하세요."""
    raise NotImplementedError("예외 핸들러 등록 로직을 구현하세요.")
