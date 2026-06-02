from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

@dataclass
class ChestActivityEvent:
    id: str
    tsMs: int
    phase: Literal[
        "idle",
        "listening",
        "thinking",
        "searching",
        "reading",
        "analyzing",
        "acting",
        "speaking",
        "success",
        "error",
    ]
    source: Literal["runtime", "planner", "debate", "browser", "vision", "tts", "safety"]
    title: str
    detail: Optional[str] = None
    progress: Optional[float] = None
    severity: Optional[Literal["info", "warning", "error"]] = "info"
    emotion: Optional[
        Literal[
            "idle",
            "listening",
            "thinking",
            "searching",
            "analyzing",
            "speaking",
            "success",
            "error",
        ]
    ] = None
    artifacts: Optional[Dict[str, Any]] = field(default_factory=dict)
    analysis: Optional[Dict[str, Any]] = field(default_factory=dict)
    action: Optional[Dict[str, Any]] = field(default_factory=dict)
