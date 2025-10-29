"""구조화 로깅 설정.

TODO:
1. `structlog` 또는 표준 로깅으로 JSON 로그 포맷을 구성하세요.
2. Uvicorn/FastAPI 로거와 수준을 일관되게 맞추세요.
3. 요청 ID/세션 ID 등의 컨텍스트 변수를 바인딩하세요.
"""

from __future__ import annotations


def configure_logging() -> None:
    """TODO: 애플리케이션 시작 시 호출되는 로깅 초기화 함수를 구현하세요."""
    raise NotImplementedError("logging 설정을 작성하세요.")
