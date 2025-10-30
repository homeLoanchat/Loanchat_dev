# orchestration/composer.py
# 템플릿 파일이 없어도 동작하도록 폴백 포함

from pathlib import Path
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
계산 결과
- 예상 한도: {{ limit_kr }}
- 금리: {{ rate }}%
- 기간: {{ term_years }}년
- 방식: {{ repay_type }}
{%- else -%}
요약
{{ summary }}

내용
{{ details }}
{%- endif -%}
"""

def _load_template() -> Template:
    path = PROMPTS / "composer_answer.txt"
    if path.exists():
        return Template(path.read_text(encoding="utf-8"))
    return Template(_FALLBACK)

def render_answer(state: OrchestrationState) -> str:
    t = _load_template()
    if state.mode == "calc":
        return t.render(
            mode="calc",
            limit_kr=state.calc.get("limit_kr", "-"),
            rate=state.calc.get("rate", "-"),
            term_years=state.calc.get("term_years", "-"),
            repay_type=state.calc.get("repay_type", "-"),
            sources=state.sources or [],
        )
    return t.render(
        mode="info",
        summary="요청하신 정보를 정리했어요.",
        details="필요 시 지역/소득/규제 조건을 알려주면 더 정확히 설명해.",
        sources=state.sources or [],
    )
