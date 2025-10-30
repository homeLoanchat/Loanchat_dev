"""간단한 구조화 로깅 설정.

Iteration 0에서는 표준 라이브러리 로깅 설정만 적용한다. 이후 Iteration에서
JSON 포맷 및 컨텍스트 바인딩을 확장할 예정이다.
"""

from __future__ import annotations

import logging
from logging.config import dictConfig

_CONFIGURED = False


def configure_logging() -> None:
    """FastAPI 서버 기동 시 한 번만 로깅 구성을 적용한다."""

    global _CONFIGURED

    if _CONFIGURED:
        return

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s [%(levelname)s] %(name)s - %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"level": "INFO", "handlers": ["console"]},
            "loggers": {
                "uvicorn": {"level": "INFO"},
                "uvicorn.error": {"level": "INFO"},
                "uvicorn.access": {"level": "INFO"},
            },
        }
    )

    _CONFIGURED = True

    logging.getLogger(__name__).info("Logging configured")
