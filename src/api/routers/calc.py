"""/calc 라우터.

TODO:
1. 계산 유형(enum)과 입력 스키마를 정의하세요.
2. `src.compute.engine`의 계산 함수를 주입받아 실행하세요.
3. 입력 검증 실패 시 사용자 친화적인 오류 메시지를 반환하세요.
4. 계산 결과에 대한 단위/포맷을 명확히 정의하세요.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/calc", tags=["calc"])


@router.post("/")
def calc_endpoint() -> dict[str, str]:
    """TODO: 계산 엔진을 호출하고 결과를 반환하세요."""
    raise NotImplementedError("calc 엔드포인트를 구현하세요.")
