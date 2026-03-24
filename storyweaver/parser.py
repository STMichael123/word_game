from __future__ import annotations

import json
import re
from typing import Any, Optional, Tuple

from .schema import LLMTurn


_JSON_BLOCK = re.compile(r"\{[\s\S]*\}$")


def _extract_json(text: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    # If model wraps JSON in ```...```
    if "```" in t:
        parts = re.split(r"```(?:json)?", t, flags=re.IGNORECASE)
        # Try last code fence content
        if len(parts) >= 2:
            candidate = parts[1].strip()
            candidate = candidate.split("```")[0].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return candidate
    m = _JSON_BLOCK.search(t)
    if m:
        return m.group(0)
    if t.startswith("{") and t.endswith("}"):
        return t
    return None


def parse_llm_turn(text: str) -> Tuple[Optional[LLMTurn], dict[str, Any]]:
    debug: dict[str, Any] = {"raw": text}
    js = _extract_json(text)
    debug["json_extracted"] = js is not None
    if not js:
        return None, debug
    try:
        obj = json.loads(js)
        debug["json_loaded"] = True
    except Exception as e:
        debug["json_loaded"] = False
        debug["json_error"] = repr(e)
        return None, debug
    try:
        turn = LLMTurn.model_validate(obj)
        debug["validated"] = True
        return turn, debug
    except Exception as e:
        debug["validated"] = False
        debug["validation_error"] = repr(e)
        return None, debug

