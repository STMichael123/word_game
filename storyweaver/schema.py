from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class LLMOption(BaseModel):
    id: str = Field(..., description="Unique id like o1")
    text: str
    intent: str
    target: Optional[str] = None
    risk: Optional[str] = None


class LLMTurn(BaseModel):
    narration: str
    options: list[LLMOption] = Field(min_length=2, max_length=4)
    memory_summary: str = Field(default="", description="One-sentence memory summary for storage")

