# LoanBot FastAPI 백엔드

금융 상담용 RAG 에이전트를 위한 FastAPI 기반 백엔드입니다.  
챗봇(`/api/chat`), 계산(`/api/calc`), 관리(`/api/admin`) API와 문서/임베딩 빌드 스크립트를 제공합니다.

---

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # 필요한 값 채우기
uvicorn src.api.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>
- 헬스 체크: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/health -H 'X-Admin-Token: <토큰>'`

### 필수 환경 변수 (`.env`)

| 변수 | 예시 | 설명 |
| --- | --- | --- |
| `ENV` | `local` | 실행 환경 식별자 |
| `PORT` | `8000` | uvicorn 포트 |
| `LOG_LEVEL` | `INFO` | 루트 로그 레벨 |
| `LOANBOT_ALLOWED_ORIGINS` | `http://localhost:5173` | CORS 허용 origin(쉼표 구분) |
| `ADMIN_SECRET` | `super-secret-token` | 관리자 API 토큰 (`X-Admin-Token`) |
| `VECTORSTORE_PATH` | `./data/vectorstore` | 벡터스토어 디렉터리 |
| `WEBSEARCH_API_KEY` | _옵션_ | 외부 웹 검색 키 |
| `METRICS_WINDOW` | `1000` | 메트릭 히스토리 최대 길이 |

`.env.example`에 기본 템플릿이 포함되어 있습니다.

---

## API 요약

### `/api/chat` – 통합 챗봇 (POST)

```json
{
  "message": "전세자금대출 한도가 궁금해요",
  "intent": "informational",
  "category": "loan_limit"
}
```

응답은 공통 포맷으로 반환됩니다.

```json
{
  "success": true,
  "type": "informational",
  "category": "loan_limit",
  "data": {
    "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
    "sources": ["https://example.com/loan-guidelines"]
  },
  "metadata": {
    "mock": true,
    "generated_at": "2025-10-30T06:52:46.910280Z",
    "trace_id": "ad7d1c28-6a2c-4a7b-86b7-5d7e65a9f6c3"
  }
}
```

### `/api/calc` – 계산 전용 (POST)

```bash
curl -X POST http://localhost:8000/api/calc \
  -H 'Content-Type: application/json' \
  -d '{
        "calc_type": "ltv",
        "params": {"collateral_value": 500000000, "loan_amount": 300000000}
      }'
```

성공 시:

```json
{
  "success": true,
  "type": "ltv",
  "data": {
    "ltv": 0.6,
    "ratio": "0.6000",
    "collateral_value": 500000000.0,
    "loan_amount": 300000000.0
  }
}
```

오류 규칙:

| 상황 | HTTP | 코드 | 비고 |
| --- | --- | --- | --- |
| 잘못된 `calc_type` | 400 | `INVALID_VALUE` | `details.calc_type` 포함 |
| 필수 파라미터 누락 | 400 | `INVALID_VALUE` | `field` 값으로 파라미터명 제공 |
| 스키마 오류 (타입 불일치 등) | 422 | `INVALID_VALUE` | FastAPI 기본 ValidationError |

지원하는 `calc_type` 값: `ltv`, `dti`, `dsr`, `amortization`, `payment_sensitivity`

### `/api/admin`

모든 엔드포인트는 `X-Admin-Token` 헤더로 보호됩니다.

| 엔드포인트 | 설명 |
| --- | --- |
| `GET /api/admin/health` | 헬스 체크 (200) |
| `POST /api/admin/reindex` | 벡터 인덱스 재생성 (202 Accepted) |
| `GET /api/admin/metrics` | 업타임/요청 수/레이턴시/토큰 사용량/마지막 재색인 시각 |

예시:

```bash
curl -X GET http://localhost:8000/api/admin/metrics \
  -H 'X-Admin-Token: super-secret-token'
```

---

## 서비스 구조

```
src/
├─ api/            # FastAPI 라우터 & 스키마
├─ core/           # 공통 응답, 예외, DI, 메트릭, 로깅
├─ services/       # ChatService, ComputeService, Retriever 래퍼
├─ compute/        # 금융 계산 엔진 및 정책 룰
├─ retrieval/      # 문서 로딩/청킹/임베딩 파이프라인
├─ orchestration/  # LangGraph 상태/라우터/컴포저 뼈대
├─ store/          # DAO 인터페이스(미구현 템플릿)
└─ websearch/      # 화이트리스트 웹 검색 템플릿
```

---

## 스크립트 & CLI

| 명령 | 설명 |
| --- | --- |
| `python scripts/build_index.py` | raw → processed → 벡터스토어 업서트 |
| `python scripts/cli.py build-index` | Typer CLI 래퍼 (exit code 0/1) |
| `python scripts/refresh_kb.py` | (미구현) 증분 KB 리프레시 |
| `python scripts/evaluate.py` | (미구현) 오프라인 평가 |

---

## 테스트

```bash
# 계산/챗봇 E2E
pytest tests/e2e/test_chat_api.py tests/e2e/test_calc_api.py

# 계산 엔진 단위 테스트
PYTHONPATH=$(pwd) pytest tests/unit
```

`tests/conftest.py`에서 ADMIN_SECRET 등 테스트용 환경 변수를 자동으로 설정합니다.

---

## 주의 사항

- `/api/chat` 계산 흐름은 Mock 구현이며, `/api/calc`를 통해 실제 ComputeService를 연결할 수 있습니다.
- `/api/admin/reindex`는 백그라운드 태스크로 수행되며, 완료 여부는 로그 또는 `last_reindex_at`으로 확인하세요.
- Admin 토큰과 외부 API 키는 반드시 환경 변수로만 주입하고 코드에 하드코딩하지 마세요.
