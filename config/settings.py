"""FastAPI 및 LangChain 전역 설정을 관리하는 모듈.

TODO:
1. `pydantic_settings.BaseSettings`를 상속한 설정 클래스를 정의하세요.
2. API 키/엔드포인트/모델 이름 등 민감 정보는 환경변수 기반으로 불러오세요.
3. 로컬/스테이징/프로덕션 프로필을 나누고, `load_dotenv` 또는 `.env`를 활용하세요.
4. `functools.lru_cache`를 이용해 싱글톤 설정 팩토리를 제공하세요.
"""

from __future__ import annotations

if __name__ == "__main__":
    raise SystemExit("이 모듈은 직접 실행하지 말고 import 해서 사용하세요.")
