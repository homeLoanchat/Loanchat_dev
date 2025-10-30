# orchestration/state.py
# 최소 의존성: 표준 라이브러리만 사용 (pydantic 제거)

from dataclasses import dataclass, field
from typing import Literal, TypedDict, List, Dict, Any, Optional

class Message(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str

@dataclass
class OrchestrationState:
    user_query: str
    mode: Optional[Literal["calc", "info"]] = None
    inputs: Dict[str, Any] = field(default_factory=dict)
    docs: List[Dict[str, Any]] = field(default_factory=list)
    calc: Dict[str, Any] = field(default_factory=dict)
    sources: List[Dict[str, str]] = field(default_factory=list)
