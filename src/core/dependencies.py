"""FastAPI 의존성 주입 모듈."""

from __future__ import annotations

from collections.abc import Generator


def get_settings():
    """TODO: `config.settings`에서 설정 객체를 불러오는 의존성을 구현하세요."""
    raise NotImplementedError("설정 의존성을 구현하세요.")


def get_vectorstore() -> Generator[object, None, None]:
    """TODO: 벡터스토어 세션을 생성/정리하는 FastAPI dependency를 구현하세요."""
    raise NotImplementedError("벡터스토어 의존성을 구현하세요.")
