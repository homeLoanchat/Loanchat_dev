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
    - 멘토님들께서 어플리케이션 실행을 위해 확인해야 할 환경설정 값 등도 반드시 PR 부가 설명란 혹은 README.md에 작성 부탁 드립니다.
    - **Pull Request에서 제출 후 절대 병합(Merge)하지 않도록 주의하세요!**
    - 수행 및 제출 과정에서 문제가 발생한 경우, 바로 강사님에게 얘기하세요! 

### FastAPI 개발 서버 실행 방법
- 의존성 설치: `pip install -r requirements.txt`
- 서버 실행: `uvicorn src.api.main:app --reload`
- 대시보드 확인: 브라우저에서 `http://localhost:8000/docs`

- `GET /api/admin/health`: 헬스체크(예: `{"status": "ok", "timestamp": "2024-01-01T00:00:00+00:00"}`)

```jsonc
// POST /api/chat 요청 예시
{
  "message": "대출 한도가 궁금해",
  "intent": "informational",
  "category": "loan_limit"
}

// 200 OK 응답 예시
{
  "result": {
    "intent": "informational",
    "payload": {
      "answer": "대출 한도는 소득과 신용등급에 따라 달라집니다.",
      "sources": [
        "https://example.com/loan-guidelines",
        "https://example.com/credit-score"
      ]
    }
  },
  "messages": [
    {
      "role": "assistant",
      "content": "정보형 답변을 생성했습니다."
    }
  ],
  "trace_id": "73f73543-5470-4f1e-9df6-b2e8de58764b",
  "meta": {
    "mock": true,
    "generated_at": "2024-01-01T00:00:00+00:00"
  }
}
```
