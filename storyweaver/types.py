from __future__ import annotations

from enum import Enum
from typing import Any, Optional, TypedDict


class Intent(str, Enum):
    EXPLORE = "explore"
    NEGOTIATE = "negotiate"
    COMBAT = "combat"
    QUERY = "query"
    REST = "rest"
    TRAVEL = "travel"
    USE_ITEM = "use_item"
    INVENTORY = "inventory"
    UNKNOWN = "unknown"


class Option(TypedDict):
    id: str
    text: str
    intent: str
    target: Optional[str]
    risk: Optional[str]


class TurnResult(TypedDict):
    narration: str
    options: list[Option]
    debug: dict[str, Any]
    system_messages: list[str]

