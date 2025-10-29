"""/chat 라우터.

TODO:
1. 사용자 메시지 스키마(요청/응답)를 Pydantic 모델로 정의하세요.
2. LangGraph 실행기 혹은 LangChain 체인을 주입받아 실행하세요.
3. 토큰/레이턴시 메트릭 수집을 `src.core.metrics`와 연동하세요.
4. 오류 발생 시 `src.core.exceptions`에 정의한 도메인 예외를 활용하세요.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/")
def chat_endpoint() -> dict[str, str]:
    """TODO: LangGraph 워크플로를 호출해 응답을 생성하세요."""
    raise NotImplementedError("chat 엔드포인트를 구현하세요.")
