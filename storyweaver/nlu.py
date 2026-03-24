from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .types import Intent


_INTENT_RULES: list[tuple[Intent, list[str]]] = [
    (Intent.INVENTORY, ["背包", "物品", "inventory", "包裹"]),
    (Intent.USE_ITEM, ["使用", "服用", "吃", "喝", "use"]),
    (Intent.TRAVEL, ["去", "前往", "赶往", "回", "入", "出发", "travel"]),
    (Intent.EXPLORE, ["探索", "探查", "搜", "查看", "巡", "潜入", "explore"]),
    (Intent.NEGOTIATE, ["交涉", "谈判", "说服", "求情", "拜访", "询价", "negotiate", "求见"]),
    (Intent.QUERY, ["打听", "询问", "问", "情报", "消息", "query"]),
    (Intent.COMBAT, ["战", "打", "杀", "出手", "比武", "combat", "袭击", "埋伏"]),
    (Intent.REST, ["休息", "睡", "打坐", "疗伤", "rest", "歇"]),
]


@dataclass(frozen=True)
class IntentGuess:
    intent: Intent
    confidence: float


@dataclass(frozen=True)
class TargetGuess:
    target: Optional[str]
    confidence: float


def classify_intent(user_text: str) -> Intent:
    return classify_intent_detailed(user_text).intent


def classify_intent_detailed(user_text: str) -> IntentGuess:
    t = (user_text or "").strip().lower()
    if not t:
        return IntentGuess(Intent.UNKNOWN, 0.0)

    # Prefer stronger action verbs and longer-keyword hits first.
    best: Optional[IntentGuess] = None
    for intent, keys in _INTENT_RULES:
        matches = [k for k in keys if k in t]
        if not matches:
            continue
        longest = max(len(k) for k in matches)
        confidence = min(0.95, 0.45 + 0.08 * len(matches) + 0.03 * longest)
        guess = IntentGuess(intent, confidence)
        if best is None or guess.confidence > best.confidence:
            best = guess

    if best is not None:
        # Avoid overconfident classification for very short free text.
        if len(t) <= 2:
            return IntentGuess(best.intent, min(best.confidence, 0.55))
        return best

    if re.fullmatch(r"\d+", t):
        return IntentGuess(Intent.UNKNOWN, 0.2)
    return IntentGuess(Intent.UNKNOWN, 0.25)


def extract_target(user_text: str) -> Optional[str]:
    return extract_target_detailed(user_text).target


def extract_target_detailed(user_text: str) -> TargetGuess:
    t = (user_text or "").strip()
    if not t:
        return TargetGuess(None, 0.0)

    m = re.search(r"(?:去|前往|赶往|回到|回)([\u4e00-\u9fff]{2,8})", t)
    if m:
        return TargetGuess(m.group(1), 0.9)

    m = re.search(r"(?:与|找|拜访|求见|询问)([\u4e00-\u9fff]{2,6})", t)
    if m:
        return TargetGuess(m.group(1), 0.8)

    m = re.search(r"(?:使用|服用|吃|喝)([\u4e00-\u9fffA-Za-z0-9]{1,12})", t)
    if m:
        return TargetGuess(m.group(1), 0.75)

    m = re.search(r"(?:调查|追查|盯住|跟踪|观察)([\u4e00-\u9fff]{2,8})", t)
    if m:
        return TargetGuess(m.group(1), 0.7)

    return TargetGuess(None, 0.2)

