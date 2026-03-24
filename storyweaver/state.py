from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


@dataclass
class GameState:
    # Core
    name: str = "无名客"
    location: str = "青石镇"
    day: int = 1

    # Stats
    health: int = 100
    max_health: int = 100
    stamina: int = 100
    max_stamina: int = 100
    reputation: int = 0
    silver: int = 30

    # Progression
    sect: Optional[str] = None
    martial_level: int = 1
    inner_power: int = 0

    # Collections
    inventory: list[str] = field(default_factory=lambda: ["粗布衣", "竹笛"])
    flags: dict[str, Any] = field(default_factory=dict)
    relations: dict[str, int] = field(default_factory=dict)  # npc -> affinity
    known_facts: dict[str, Any] = field(default_factory=dict)  # canonical facts for consistency

    # Logs
    event_history: list[dict[str, Any]] = field(default_factory=list)
    last_options: list[dict[str, Any]] = field(default_factory=list)

    def push_event(self, kind: str, summary: str, data: Optional[dict[str, Any]] = None) -> None:
        self.event_history.append(
            {
                "t": _now_iso(),
                "kind": kind,
                "summary": summary,
                "data": data or {},
            }
        )

    def compact_history(self, keep_last: int) -> None:
        if keep_last <= 0:
            self.event_history = []
        elif len(self.event_history) > keep_last:
            self.event_history = self.event_history[-keep_last:]

        # Keep narrative memory bounded so save files and prompt payload stay small.
        story_memory = self.flags.get("story_memory")
        if isinstance(story_memory, list) and len(story_memory) > 80:
            self.flags["story_memory"] = story_memory[-80:]

        fact_events = self.flags.get("fact_events")
        if isinstance(fact_events, list) and len(fact_events) > 120:
            self.flags["fact_events"] = fact_events[-120:]

        story_narrations = self.flags.get("story_narrations")
        if isinstance(story_narrations, list) and len(story_narrations) > 30:
            self.flags["story_narrations"] = story_narrations[-30:]

        story_narrations_recent = self.flags.get("story_narrations_recent")
        if isinstance(story_narrations_recent, list) and len(story_narrations_recent) > 30:
            self.flags["story_narrations_recent"] = story_narrations_recent[-30:]

        # Archive is for export completeness; keep it much larger to avoid early data loss.
        story_narrations_archive = self.flags.get("story_narrations_archive")
        if isinstance(story_narrations_archive, list) and len(story_narrations_archive) > 2000:
            self.flags["story_narrations_archive"] = story_narrations_archive[-2000:]

    def to_public_dict(self) -> dict[str, Any]:
        raw_story_memory = self.flags.get("story_memory")
        stage_idx = int(self.flags.get("stage_idx", 0))
        story_memory_recent: list[dict[str, Any]] = []
        if isinstance(raw_story_memory, list):
            current_stage_entries = [x for x in raw_story_memory if isinstance(x, dict) and int(x.get("stage_idx", stage_idx)) == stage_idx]
            previous_stage_entries = [x for x in raw_story_memory if isinstance(x, dict) and int(x.get("stage_idx", stage_idx)) == stage_idx - 1]
            if current_stage_entries:
                story_memory_recent = [*previous_stage_entries[-4:], *current_stage_entries[-8:]]
            else:
                story_memory_recent = raw_story_memory[-12:]

        raw_fact_events = self.flags.get("fact_events")
        fact_events_recent = raw_fact_events[-8:] if isinstance(raw_fact_events, list) else []
        raw_npc_registry = self.flags.get("npc_registry")
        npc_registry = raw_npc_registry if isinstance(raw_npc_registry, dict) else {}
        progress = int(self.flags.get("progress", 0))
        turn = int(self.flags.get("turn", 0))
        return {
            "name": self.name,
            "location": self.location,
            "day": self.day,
            "stats": {
                "health": self.health,
                "max_health": self.max_health,
                "stamina": self.stamina,
                "max_stamina": self.max_stamina,
                "reputation": self.reputation,
                "silver": self.silver,
                "martial_level": self.martial_level,
                "inner_power": self.inner_power,
                "sect": self.sect,
            },
            "inventory": list(self.inventory),
            "relations": dict(self.relations),
            "known_facts": dict(self.known_facts),
            "recent_events": list(self.event_history[-8:]),
            "story_memory_recent": story_memory_recent,
            "fact_events_recent": fact_events_recent,
            "npc_registry": npc_registry,
            "progress": progress,
            "stage_idx": stage_idx,
            "turn": turn,
            "active_side_quests": list(self.flags.get("active_side_quests", [])),
            "done_side_quests": list(self.flags.get("done_side_quests", [])),
            "final_clear": bool(self.flags.get("final_clear")),
            "ending": self.flags.get("ending"),
        }

    def to_save_json(self) -> str:
        payload = {
            "version": 1,
            "saved_at": _now_iso(),
            "state": self.__dict__,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def from_save_json(s: str) -> "GameState":
        payload = json.loads(s)
        st = GameState()

        data = payload.get("state", {})
        if not isinstance(data, dict):
            return st

        if isinstance(data.get("name"), str):
            st.name = data["name"]
        if isinstance(data.get("location"), str):
            st.location = data["location"]
        if isinstance(data.get("sect"), (str, type(None))):
            st.sect = data["sect"]

        int_fields = [
            "day",
            "health",
            "max_health",
            "stamina",
            "max_stamina",
            "reputation",
            "silver",
            "martial_level",
            "inner_power",
        ]
        for field_name in int_fields:
            v = data.get(field_name)
            if isinstance(v, int):
                setattr(st, field_name, v)

        inv = data.get("inventory")
        if isinstance(inv, list):
            st.inventory = [x for x in inv if isinstance(x, str)]

        flags = data.get("flags")
        if isinstance(flags, dict):
            st.flags = flags

        relations = data.get("relations")
        if isinstance(relations, dict):
            st.relations = {str(k): int(v) for k, v in relations.items() if isinstance(v, int)}

        known_facts = data.get("known_facts")
        if isinstance(known_facts, dict):
            st.known_facts = known_facts

        event_history = data.get("event_history")
        if isinstance(event_history, list):
            st.event_history = [x for x in event_history if isinstance(x, dict)]

        last_options = data.get("last_options")
        if isinstance(last_options, list):
            st.last_options = [x for x in last_options if isinstance(x, dict)]

        return st

