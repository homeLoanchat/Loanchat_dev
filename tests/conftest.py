from __future__ import annotations

import os

def pytest_configure() -> None:  # pragma: no cover - 테스트 초기 설정
    os.environ.setdefault("ADMIN_SECRET", "test-secret")
    os.environ.setdefault("LOANBOT_ALLOWED_ORIGINS", "*")
