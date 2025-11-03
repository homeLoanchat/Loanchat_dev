"""FastAPI 의존성 주입 모듈."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from config.settings import Settings, get_settings as _load_settings


def get_settings() -> Settings:
    """설정 객체를 FastAPI dependency로 노출한다."""

    return _load_settings()


@contextmanager
def _vectorstore_context() -> Generator[Any | None, None, None]:
    """벡터스토어 세션 컨텍스트의 자리표시자."""

    yield None


def get_vectorstore() -> Generator[Any | None, None, None]:
    """FastAPI dependency로 사용할 벡터스토어 세션."""

    with _vectorstore_context() as resource:
        yield resource


__all__ = ["get_settings", "get_vectorstore"]
