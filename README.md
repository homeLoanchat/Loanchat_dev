# 토이 프로젝트 4 : RAG를 이용하여 Knowledge Base와 Web Search를 활용한 정확한 지식 기반 답변을 하는 Agent 시스템 개발
### [프로젝트 개요] 
- **프로젝트 명** : RAG를 이용하여 Knowledge Base와 Web Search를 활용한 정확한 지식 기반 답변을 하는 Agent 시스템 개발
- **상세 내용 :** [프로젝트 RFP 노션 링크](https://www.notion.so/Toy-Project-4-26c9047c353d8064b6abe1419d3d6d1a)
- **수행 및 결과물 제출 기한** : 10/24 (금) ~ 11/6 (목) 18:00
- **코드리뷰 기한** : 11/10 (월) ~ 11/17 (월), 1주 간 진행 


### [프로젝트 진행 및 제출 방법]
- 본 패스트캠퍼스 Github의 Repository를 각 조별의 Github Repository를 생성 후 Fork합니다.
    - 패스트캠퍼스 깃헙은 Private 형태 (Public 불가)
- 조별 레포의 최종 branch → 패스트캠퍼스 업스트림 Repository의 main branch의 **PR 상태**로 제출합니다.
    - **PR TITLE : N조 최종 제출**
    - Pull Request 링크를 LMS로도 제출해 주셔야 최종 제출 완료 됩니다. (제출자: 조별 대표자 1인)
    - LMS를 통한 과제 미제출 시 점수가 부여되지 않습니다. 
- PR 제출 시 유의사항
    - 프로젝트 진행 결과 및 과업 수행 내용은 README.md에 상세히 작성 부탁 드립니다. 
    - 멘토님들께서 어플리케이션 실행을 위해 확인해야 할 환경설정 값 등도 반드시 PR 부가 설명란 혹은 README.md에 작성 부탁 드립니다.
    - **Pull Request에서 제출 후 절대 병합(Merge)하지 않도록 주의하세요!**
    - 수행 및 제출 과정에서 문제가 발생한 경우, 바로 강사님에게 얘기하세요! 

## FastAPI 서버 실행

필수 의존성은 `requirements.txt`에 정리되어 있습니다.

```bash
uvicorn src.api.main:app --reload
```

서버가 기동되면 Swagger UI는 `http://localhost:8000/docs`에서 확인 가능합니다.

### 샘플 요청

`intent` 값은 `informational` 또는 `calculational` 두 가지를 지원합니다.

```bash
http POST :8000/api/chat type=informational message='전세자금대출 한도'

curl -X POST http://localhost:8000/api/chat \
    -H 'Content-Type: application/json' \
    -d '{"message":"전세자금대출 한도가 궁금해요","intent":"informational"}'
```

요청 바디 예시:

```json
{
  "message": "대출 한도가 궁금해요",
  "intent": "informational",
  "category": "loan_limit"
}
```

응답 예시:

```json
{
  "result": {
    "intent": "informational",
    "payload": {
      "type": "informational",
      "content": {
        "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
        "sources": [
          "https://example.com/loan-guidelines",
          "https://example.com/credit-score"
        ]
      }
    }
  },
  "messages": [
    {
      "role": "assistant",
      "content": "정보형 답변을 생성했습니다."
    }
  ],
  "trace_id": "ad7d1c28-6a2c-4a7b-86b7-5d7e65a9f6c3",
  "meta": {
    "mock": true,
    "generated_at": "2025-10-30T06:52:46.910280Z"
  }
}
```

헬스체크는 다음 명령으로 확인할 수 있습니다.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/admin/health
```

### Mock 서비스 구조

Iteration 2에서는 라우터에서 직접 payload를 구성하지 않고 `ChatService`를 통해
Mock 모듈을 호출합니다.

- Retrieval Mock: `retriever.run(category, query, *, user_id=None) -> dict`
- Compute Mock: `compute.run(category, params, *, user_id=None) -> dict`

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

향후 실제 Retrieval/Compute 모듈이 준비되면 `get_chat_service()`에서 주입하는
구현체만 교체하면 됩니다.
