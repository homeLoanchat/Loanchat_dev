# LoanChat Backend

FastAPI 기반으로 구축한 주택담보대출 상담용 챗봇 백엔드입니다.  
정보형 질문은 RAG 파이프라인과 웹 검색을 활용하고, 계산형 질문은 금융 계산 엔진으로 처리합니다.  
응답 단계별 검증과 사용자 친화적인 요약이 포함된 것이 특징입니다.

---

## 주요 기능
- **통합 챗봇 API** (`POST /api/chat`)  
  - 도메인 필터 → 의도/슬롯 판별 → 정보형·계산형 브랜치 처리 → 검증 결과와 메트릭을 포함한 표준 응답 반환
- **계산 전용 API** (`POST /api/calc`)  
  - LTV, DTI, DSR, 원리금 균등 상환, 금리 민감도 계산을 직접 호출
- **웹 검색 연동**  
  - SerpAPI를 통한 최신 정보 보강, 키 누락 시 검증에서 탐지하여 안전한 폴백 메시지 제공
- **관리/모니터링 API** (`/api/admin/*`)  
  - 헬스 체크, 벡터 인덱스 재생성, 메트릭 확인
- **문서 파이프라인 스크립트**  
  - `scripts/build_index.py`로 문서 로딩 → 청킹 → 임베딩 → ChromaDB 업서트

---

## 기술 스택
| 영역 | 사용 기술 |
| --- | --- |
| Language / Runtime | Python 3.11, asyncio/uvloop |
| API / App | FastAPI, Uvicorn, Pydantic, Typer |
| Retrieval / RAG | LangChain 유틸, ChromaDB, SerpAPI, 커스텀 `RetrievalPipeline` |
| LLM / Embedding | Upstage Solar-Pro2 Chat API, Upstage Embedding API (hash 폴백 포함) |
| 금융 계산 | 순수 Python 계산 엔진 (`src/compute/engine.py`) + Optional pandas |
| 환경 / 설정 | pydantic-settings, python-dotenv, YAML 설정 파일 |
| 테스트 / 품질 | pytest, pytest-asyncio |

---

## 디렉터리 구조
```
src/
├─ api/            # FastAPI 라우터 및 Pydantic 스키마
├─ core/           # 공통 응답, 예외, 로깅, 메트릭 유틸
├─ services/       # ChatService, ComputeService, Retriever 래퍼, Upstage 클라이언트
├─ compute/        # 금융 계산 엔진 및 정책 로직
├─ retrieval/      # 문서 청킹, 임베딩, 벡터스토어 파이프라인
├─ websearch/      # SerpAPI 설정, 화이트리스트, 요청 프로바이더
└─ scripts/        # 인덱스 빌드, CLI, 향후 고도화 스크립트
```

---

## 파이프라인 개요

```
사용자 질문
  └─ 주담대 도메인 필터 → 비도메인 안내문 반환
       └─ 의도/슬롯 판별
            ├─ 정보형 브랜치: 벡터 검색 → 검증 → 필요 시 웹 검색 → 요약 응답
            └─ 계산형 브랜치: 파라미터 정규화 → 계산 유형 추론 → 금융 계산 → 검증 → 자연어 요약
```

- 모든 결과에는 `validation`, `metrics.intent`, `metrics.validation` 등이 포함되어 추적이 용이합니다.
- 계산형 응답은 “예상 월 상환액은 …”처럼 요약 문장을 생성하며 부족한 정보가 있으면 구조화된 입력 요청을 내려보냅니다.

---

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .\.venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env           # 환경 변수 채우기
uvicorn src.api.main:app --reload
```

- Swagger UI: <http://localhost:8000/docs>  
- 헬스 체크: `curl -H 'X-Admin-Token: <토큰>' http://localhost:8000/api/admin/health`

---

## 환경 변수 (.env)

| 변수 | 예시 | 설명 |
| --- | --- | --- |
| `ENV` | `local` | 실행 환경 식별 |
| `PORT` | `8000` | Uvicorn 포트 |
| `LOG_LEVEL` | `INFO` | 루트 로그 레벨 |
| `ADMIN_SECRET` | `super-secret-token` | 관리자 API 토큰 |
| `VECTORSTORE_PATH` | `./data/vectorstore` | ChromaDB 저장 위치 |
| `SERPAPI_KEY` | `...` | 웹 검색 API 키 (선택) |
| `UPSTAGE_API_KEY` | `...` | Upstage Chat/Embedding 키 |
| `UPSTAGE_CHAT_MODEL` | `solar-pro2` | 챗봇 모델 지정 (선택) |

`python-dotenv`가 자동으로 `.env`를 로딩하며, `ChatService`는 워커 프로세스에서도 한번만 초기화되도록 가드합니다.

---

## API 요약

### `/api/chat` (POST)
```json
{
  "message": "주담대 갈아타기 조건이 궁금해",
  "category": null,
  "params": null
}
```
- 정보형: `data.answer`, `sources`, `confidence`, `validation` 포함
- 계산형: `data.result`, `summary`, `answer`, `needs_input`, `calc_type_options` 등 포함

### `/api/calc` (POST)
```bash
curl -X POST http://localhost:8000/api/calc \
  -H "Content-Type: application/json" \
  -d '{"calc_type":"ltv","params":{"collateral_value":500000000,"loan_amount":300000000}}'
```
- 성공 시 비율·입력 값을 함께 반환
- 오류 시 `INVALID_VALUE` 코드와 필드 정보를 리턴

### `/api/admin`
| Method | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/admin/health` | 헬스 체크 |
| GET | `/api/admin/metrics` | 요청 수, 지연, 토큰 사용량, 마지막 인덱스 시각 |
| POST | `/api/admin/reindex` | 문서 인덱스 재생성 (백그라운드 태스크) |

모든 관리자 API는 `X-Admin-Token` 헤더가 필요합니다.

---

## 문서 인덱스 파이프라인

```bash
python scripts/build_index.py \
  --raw-dir data/raw \
  --output-dir data/processed \
  --skip-vectorstore False
```

- 문서를 로드해 JSONL(`chunks.jsonl`, `documents.json`)로 저장
- Upstage Embedding API → ChromaDB에 업서트
- `config/retrieval.yaml`로 청킹 크기, 임베더, 벡터스토어 경로를 제어

---

## 테스트

```bash
# 전체 테스트
pytest

# E2E (챗봇 + 계산)
pytest tests/e2e/test_chat_api.py tests/e2e/test_calc_api.py

# 계산 엔진 단위 테스트
PYTHONPATH=$(pwd) pytest tests/unit
```

`tests/conftest.py`에서 필요한 환경 변수를 세팅합니다.

---

## 작업 시 주의 사항
- `/api/chat`의 계산형 흐름은 intent 판별에 실패하면 정제된 입력 요청 메시지를 내려보냅니다.  
  프론트엔드에서도 `data.needs_input`, `calc_type_options`를 활용해 입력 폼을 안내할 수 있습니다.
- 외부 키가 없는 경우 웹 검색은 자동으로 폴백되며 로컬 문서만 사용됩니다.
- `SERPAPI_KEY`, `UPSTAGE_API_KEY`, `ADMIN_SECRET` 등 민감 정보는 코드에 하드코딩하지 않습니다.

---

## 향후 고도화 아이디어

- 사용자 맞춤 추천(대화 이력 기반 intent 가중치)과 FAQ 템플릿 강화
- 검증 메트릭과 사용자 피드백을 연동해 자동 대시보드 구성
- 다국어/자연어 표현 확대를 위한 슬롯 추출 사전 추가
- LLM 라우팅/백업 모델 도입으로 신뢰성과 비용 최적화

---
## 아키텍쳐 다이어그램

<img width="442" height="478" alt="토이 프로젝트_4팀(Lang잔고를 부탁해)_(아키텍쳐 다이어그램)" src="https://github.com/user-attachments/assets/2da84838-45d6-4740-b66c-b43aa2e9dab7" />

## 라이선스

