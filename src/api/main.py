"""FastAPI 엔트리 포인트.

TODO:
1. `FastAPI` 인스턴스를 생성하고 CORS/미들웨어를 설정하세요.
2. lifespan 이벤트에서 설정 로드, 로거 초기화, 리소스 클린업을 구현하세요.
3. `src.api.routers`에 정의한 라우터를 include 하세요.
4. 구조화 로깅과 예외 핸들러를 `src.core` 모듈과 연결하세요.
"""

from __future__ import annotations

from fastapi import FastAPI

from src.api.routers.admin import router as admin_router
from src.api.routers.chat import router as chat_router

app = FastAPI(title="LoanBot API", version="0.1.0")

app.include_router(chat_router)
app.include_router(admin_router)
