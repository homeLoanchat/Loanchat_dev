# LoanBot RAG 에이전트

지식베이스(RAG)와 화이트리스트 웹 검색을 결합해 금융 상품 질문에 신뢰 가능한 답변을 제공하는 LoanBot 백엔드입니다.  
FastAPI 기반 REST API, LangGraph 오케스트레이션, Pandas 계산 엔진, ChromaDB 벡터스토어를 하나의 파이프라인으로 묶었습니다.

---

## 빠른 시작

### 1. 사전 준비

- Python 3.11 이상 (권장: 3.11.x)  
- (선택) 가상환경

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

- PDF 추출이 필요하면 `pip install pypdf` (또는 `PyPDF2`)를 추가 설치하세요.

### 2. 환경 변수

프로젝트 루트에 `.env`를 만들어 아래 항목을 채워주세요.  
`config/.env.example` 파일에 기본 템플릿이 포함되어 있습니다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `APP_ENV` | `local` | 실행 환경 플래그 |
| `APP_HOST` | `0.0.0.0` | FastAPI 바인딩 호스트 |
| `APP_PORT` | `8000` | FastAPI 포트 |
| `LOANBOT_ALLOWED_ORIGINS` | `*` | CORS 허용 오리진 목록 |
| `ADMIN_ACCESS_TOKEN` | 없음 | Admin API 보호용 토큰 (`X-ADMIN-TOKEN`) |
| `LLM_API_BASE` | `https://api.openai.com/v1` | OpenAI 호환 API 엔드포인트 |
| `LLM_API_KEY` | 없음 | LLM/임베딩 호출용 키 |
| `VECTOR_DB_PATH` | `./data/embeddings/chroma` | ChromaDB 저장 위치 |
| `VECTOR_DB_COLLECTION` | `loanbot_docs` | ChromaDB 컬렉션 이름 |
| `SEARCH_API_KEY` | 없음 | 외부 검색/크롤링 키 |
| `UPSTAGE_API_KEY` | 없음 | 리랭커/재순위 API 키 |
| `DATA_GO_KR_KEY` | 없음 | 공공데이터 포털 서비스 키 |
| `LOG_LEVEL` | `INFO` | 애플리케이션 로그 레벨 |
| `LANGSMITH_API_KEY` | 없음 | LangSmith 추적용 키 |

필요한 외부 서비스 키를 사용 환경에 맞게 추가하거나 비워두면 됩니다.

### 3. 서버 실행

```bash
uvicorn src.api.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>
- 헬스 체크: `curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/health`

Docker 환경을 사용하려면:

```bash
docker compose up --build
```

---

## API 개요

### `/api/chat` – 통합 챗봇 (Mock 기반)

| 항목 | 내용 |
| --- | --- |
| 메서드 | `POST` |
| 요청 | `{ "message": "...", "intent": "informational" | "calculational", "category": "...", "params": {...} }` |
| 응답 | `{ "success": true, "type": "informational", "data": {...}, "metadata": {...} }` |

샘플 호출:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"전세자금대출 한도가 궁금해요","intent":"informational","category":"loan_limit"}'
```

Retrieval 경로는 `PipelineRetriever`가 담당하며, ChromaDB에서 관련 문서를 검색한 후 Upstage 리랭커로 상위 결과를 정렬하고, 필요 시 화이트리스트 웹 검색 결과를 보강합니다. 계산 의도는 `ChatService` 내부의 ComputeRunner를 통해 Pandas 기반 순수 함수를 호출합니다.

### `/api/calc` – 계산 전용 (계약만 정의)

금융 계산을 위한 전용 엔드포인트입니다. 프런트엔드나 오케스트레이션에서 계산 엔진을 직접 호출할 수 있습니다.  
계약 세부 사항은 `docs/calc_api_contract.md`에서 유지 관리합니다.

**요청 (`POST /api/calc`)**

```json
{
  "calc_type": "amortization_schedule",
  "params": {
    "principal": 30000000,
    "interest_rate": 0.055,
    "months": 36
  }
}
```

**응답**

```json
{
  "success": true,
  "type": "amortization_schedule",
  "data": {
    "rows": [
      { "period": 1, "payment": 905877.05, "principal": 768377.05, "interest": 137500.0, "balance": 29231622.95 }
    ],
    "summary": {
      "monthly_payment": 905877.05,
      "total_payment": 32611573.95,
      "total_interest": 2611573.95
    }
  },
  "metadata": {
    "mock": false,
    "generated_at": "2025-10-30T06:53:10.123456Z",
    "trace_id": "f2e5f9ab-e268-474c-8a65-3a621ecf3a4d"
  }
}
```

헬스체크는 다음 명령으로 확인할 수 있습니다.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/health
```

### 서비스 구성

`ChatService`는 FastAPI 라우터에 의존성으로 주입되어 intent에 따라 Retrieval/Compute 경로를 실행합니다.  
Retrieval은 `PipelineRetriever`가 CRAG 임계치(최소 점수/결과 수)를 적용해 신뢰도 정보를 산출하며, Compute는 `LoanComputationService`가 정책 테이블과 계산 엔진을 결합해 한도/상환/비율 정보를 생성합니다.

FastAPI 라우터는 다음과 같이 의존성을 주입받습니다.

```python
from fastapi import Depends

from src.services import ChatService, get_chat_service


@router.post("", response_model=ChatResponse)
def chat_endpoint(
    payload: ChatRequest,
    service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    return service.handle(payload)
```

Retrieval의 신뢰도 평가는 응답 `metadata.confidence`에 기록되고, 계산형 응답은 `LoanComputationService`에서 산출한 월 상환액/비율 정보가 포함됩니다.
추가로 `/api/chat/preview` 엔드포인트는 `mode`(`info`/`calc`)에 따라 공통 구조의 미리보기 응답을 제공해, 검색 근거와 계산 결과를 사전에 확인할 수 있습니다.

## 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `python scripts/build_index.py` | raw → processed → embeddings 업서트 | — |
| `python scripts/refresh_kb.py` | 변경 문서 증분 업데이트 | — |
| `python scripts/cli.py` | Typer CLI (build/refresh/evaluate 래퍼) | 각 커맨드는 현재 `NotImplementedError` 상태 |
| `python scripts/evaluate_reranker.py` | 리랭커 품질 평가 | — |

RetrievalPipeline은 `config/retrieval.yaml` 설정을 읽어 로더/청킹/임베딩/벡터스토어 업서트를 자동화합니다.  
임베딩은 OpenAI/Text-Embedding-3 Large(기본)이며, Upstage reranker로 상위 K개 결과만 반환합니다.

---

## 테스트

```bash
# 전체 테스트
pytest

# /api/chat e2e만
pytest tests/e2e/test_chat_api.py
pytest tests/unit/test_composer.py
```

## DI 교체 방법

`src/services`에서 제공하는 `get_retriever()`/`get_compute()`를 FastAPI dependency override로 교체하면 됩니다.

```python
from src.services import get_compute, get_retriever

app.dependency_overrides[get_retriever] = lambda: MyRetriever()
app.dependency_overrides[get_compute] = lambda: MyCompute()
```

라우터 구현은 그대로 유지됩니다.
