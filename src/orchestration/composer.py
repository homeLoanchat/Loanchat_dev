# orchestration/composer.py
# 템플릿 파일이 없어도 동작하도록 폴백 포함

from pathlib import Path
from typing import Iterable, Any

from jinja2 import Template

from .state import OrchestrationState

# 폴더 위치가 바뀌어도 찾도록 후보 경로를 순회
def _find_prompts_dir() -> Path:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "prompts",   # 프로젝트 루트/prompts (권장)
        here.parents[1] / "prompts",   # src/prompts
        here.parent / "prompts",       # orchestration/prompts
    ]
    for p in candidates:
        if p.exists():
            return p
    return candidates[0]  # 없으면 루트 기준으로 반환(파일 없을 시 폴백 템플릿 사용)


PROMPTS = _find_prompts_dir()

# 폴백 템플릿(파일 없을 때 사용)
_FALLBACK = """\
{% if mode == "calc" -%}
계산 결과 요약
{{ summary }}
{% if calc.repayment %}
- 월 상환액: {{ calc.repayment.monthly_payment | default("-") }}
- 상환 기간: {{ calc.repayment.term_months | default("-") }}개월
{% endif %}
{% if calc.policy %}
- 적용 정책 한도(LTV): {{ calc.policy.ltv_limit | default("-") }}
- DTI 한도: {{ calc.policy.dti_limit | default("-") }}
{% endif %}
{% else -%}
정보 요약
{{ summary }}
{% if confidence %}
신뢰도: {{ "충족" if confidence.passed else "미충족" }}
{% if confidence.reason %}사유: {{ confidence.reason }}{% endif %}
{% endif %}
{% if sources %}
근거 출처:
{% for src in sources %}
- {{ src }}
{% endfor %}
{% endif %}
{% endif %}
"""


def _load_template() -> Template:
    path = PROMPTS / "composer_answer.txt"
    if path.exists():
        return Template(path.read_text(encoding="utf-8"))
    return Template(_FALLBACK)


def _stringify_sources(sources: Iterable[Any]) -> list[str]:
    result: list[str] = []
    for source in sources or []:
        if isinstance(source, dict):
            label = source.get("name") or source.get("title") or source.get("url") or source.get("doc_source")
            result.append(str(label) if label else str(source))
        else:
            result.append(str(source))
    return result


def render_answer(state: OrchestrationState) -> str:
    template = _load_template()
    mode = state.mode or "info"
    summary = state.response_message or state.answer or "요청하신 정보를 정리했어요."
    sources = _stringify_sources(state.sources)
    context = {
        "mode": mode,
        "state": state,
        "summary": summary,
        "calc": state.calc or {},
        "sources": sources,
        "confidence": state.confidence,
    }
    return template.render(**context)
