# `/api/calc` 계약 가이드

계산 엔진을 직접 호출하는 전용 엔드포인트(`/api/calc`)의 요청/응답 규칙과 테스트 시나리오를 정리했습니다. FastAPI 라우터 구현 시 아래 계약을 준수해 주세요.

## 요청 포맷

```jsonc
POST /api/calc
{
  "calc_type": "ltv",          // 아래 테이블 중 하나
  "params": { ... }            // calc_type별 파라미터
}
```

- `calc_type`는 계산 유형 문자열이며, 미지정 값은 400(`INVALID_VALUE`)을 반환합니다.
- `params`는 각 계산 함수가 요구하는 파라미터를 포함한 객체입니다. 모든 금액/금리/기간 값은 0 초과(또는 정책에서 허용하는 경우 0 이상)이어야 합니다.

## 응답 포맷

| 속성 | 설명 |
| --- | --- |
| `success` | 계산 성공 여부 (`true`/`false`) |
| `type` | 계산된 `calc_type` |
| `data` | 계산 결과 (success=true 일 때만 존재) |
| `error` | 실패 시 오류 코드/메시지/필드/세부 정보 |
| `metadata` | 추적용 메타데이터 (trace id, mock 여부 등) |

성공 응답 예시는 README의 샘플을 참고하세요.

## calc_type별 파라미터

| calc_type | 필수 파라미터 | 선택 파라미터 | 설명 |
|-----------|---------------|----------------|------|
| `ltv` | `collateral_value`, `loan_amount` | — | 담보 대비 대출 비율(LTV) |
| `dti` | `annual_income`, `total_debt_payment` | — | 총부채상환비율 |
| `dsr` | `annual_income`, `annual_debt_service` | — | 총부채원리금상환비율 |
| `amortization_schedule` | `principal`, `interest_rate`, `months` | `as_dataframe` | 원리금 균등 상환 스케줄 |
| `monthly_payment` | `principal`, `interest_rate`, `months` | — | 월 상환액 및 요약 값 (스케줄 기반) |
| `payment_sensitivity` | `principal`, `interest_rates[]`, `months` | `as_dataframe` | 금리 민감도 분석 |

파라미터 이름은 `src/compute/engine.py` 함수 시그니처와 동일하게 유지하는 것을 권장합니다. 추가 계산 유형을 도입하면 이 테이블과 README의 표를 함께 업데이트하세요.

## 에러 규칙

| 코드 | HTTP 상태 | 사용 조건 | message 예시 |
| --- | --- | --- | --- |
| `INVALID_VALUE` | 400 / 422 | 파라미터 누락, 음수 입력, 형식 오류 | `"interest_rate must be non-negative."` |
| `INVALID_RANGE` | 400 | 정책 한도 위반 (`policy.py`) | `"DTI exceeds allowed limit for product mortgage."` |
| `TIMEOUT` | 504 | 계산 엔진/외부 연동 지연 | `"Calculation timed out."` |

- `INVALID_VALUE`와 `INVALID_RANGE`는 `src/core/exceptions.py`에 정의된 예외 클래스를 사용해 생성합니다.
- 정책 위반 시 `error.details`에 `{"limit": 0.4, "policy": "kr.mortgage"}`처럼 근거 값을 포함해 주세요.

## E2E 테스트 샘플

`tests/e2e/test_calc_api.py`를 추가할 때 아래 시나리오를 기본으로 포함합니다.

```python
@pytest.mark.anyio
async def test_calc_ltv_success(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={
            "calc_type": "ltv",
            "params": {"collateral_value": 500_000_000, "loan_amount": 300_000_000},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["ratio"] == pytest.approx(0.6, rel=1e-6)


@pytest.mark.anyio
async def test_calc_dti_policy_violation(client: AsyncClient) -> None:
    response = await client.post(
        "/api/calc",
        json={
            "calc_type": "dti",
            "params": {"annual_income": 80_000_000, "total_debt_payment": 50_000_000},
        },
    )
    assert response.status_code == 400
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_RANGE"
    assert body["error"]["details"]["limit"] == 0.4
```

위반/성공 사례를 최소 1개씩 포함하고, 정책 한도 변동 시 테스트도 함께 업데이트합니다.
