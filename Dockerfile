# LoanBot 컨테이너 이미지 빌드용 Dockerfile
# TODO:
# 1. slim Python 베이스 이미지 선택 (예: python:3.11-slim).
# 2. 시스템 패키지 설치(빌드 도구, libmagic 등 필요 시).
# 3. pip/poetry를 이용해 의존성을 설치하세요.
# 4. `/app` 디렉터리에 소스 복사 후 `uvicorn` 또는 `gunicorn` 엔트리포인트를 설정하세요.
# 5. 멀티스테이지 빌드로 이미지 크기를 최적화하세요.
