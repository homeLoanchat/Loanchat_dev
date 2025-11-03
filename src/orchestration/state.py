# orchestration/state.py
# 최소 의존성: 표준 라이브러리만 사용 (pydantic 제거)

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional, TypedDict

class Message(TypedDict):
    role: Literal["user", "assistant", "system"]
    content: str

@dataclass
class OrchestrationState:
    user_query: str
    mode: Optional[Literal["calc", "info"]] = None
    intent: Optional[str] = None
    category: Optional[str] = None
    slots: Dict[str, Any] = field(default_factory=dict)
    inputs: Dict[str, Any] = field(default_factory=dict)
    documents: List[Dict[str, Any]] = field(default_factory=list)
    web_results: List[Dict[str, Any]] = field(default_factory=list)
    calc: Dict[str, Any] = field(default_factory=dict)
    sources: List[Any] = field(default_factory=list)
    answer: Optional[str] = None
    confidence: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    response_data: Dict[str, Any] = field(default_factory=dict)
    messages: List[Message] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    response_message: str = ""
    response_text: str = ""
