from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _normalize_doc_id(doc_id: str) -> str:
    raw = _clean_text(doc_id)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
    return safe or "default"


def _memory_timestamp_from_entry(entry: dict[str, Any]) -> str:
    direct = _clean_text(entry.get("memory_timestamp") or entry.get("time_label"))
    if direct:
        return direct

    day = entry.get("day")
    if isinstance(day, int):
        phase = "上午" if _clean_text(entry.get("time_phase")) != "夜幕" else "下午"
        return f"第{day}日{phase}"
    return ""


def _memory_index_from_entry(entry: dict[str, Any]) -> str:
    return _clean_text(entry.get("memory_index") or entry.get("summary") or entry.get("action"))


def normalize_timeline(entries: list[dict[str, Any]] | object, *, limit: int = 80) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        return []

    timeline: list[dict[str, Any]] = []
    for item in entries:
        if not isinstance(item, dict):
            continue
        normalized = {
            "turn": int(item.get("turn", 0)),
            "stage_idx": int(item.get("stage_idx", 0)),
            "stage_title": _clean_text(item.get("stage_title") or "终局"),
            "memory_timestamp": _memory_timestamp_from_entry(item),
            "memory_index": _memory_index_from_entry(item),
            "chapter_goal_effect": _clean_text(item.get("chapter_goal_effect")),
            "location": _clean_text(item.get("location")),
            "time_label": _clean_text(item.get("time_label")),
            "day": int(item.get("day", 0)) if isinstance(item.get("day"), int) else 0,
            "time_phase": _clean_text(item.get("time_phase") or "白昼"),
            "summary": _clean_text(item.get("summary") or item.get("memory_index") or item.get("action")),
            "story_significance": _clean_text(item.get("story_significance")),
            "delta_summary": _clean_text(item.get("delta_summary")),
        }
        if not normalized["memory_index"] and not normalized["summary"]:
            continue
        timeline.append(normalized)

    return timeline[-limit:]


def _build_chapter_memory(timeline: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    for entry in timeline:
        grouped.setdefault(int(entry.get("stage_idx", 0)), []).append(entry)

    chapter_memory: list[dict[str, Any]] = []
    for stage_idx in sorted(grouped):
        entries = grouped[stage_idx]
        stage_title = _clean_text(entries[-1].get("stage_title") or "终局")
        indices: list[str] = []
        for entry in entries:
            idx = _clean_text(entry.get("memory_index"))
            if idx and idx not in indices:
                indices.append(idx)

        chapter_memory.append(
            {
                "stage_idx": stage_idx,
                "stage_title": stage_title,
                "entry_count": len(entries),
                "first_turn": int(entries[0].get("turn", 0)),
                "last_turn": int(entries[-1].get("turn", 0)),
                "first_timestamp": _clean_text(entries[0].get("memory_timestamp")),
                "last_timestamp": _clean_text(entries[-1].get("memory_timestamp")),
                "summary_indices": indices[-4:],
                "summary_text": "；".join(indices[-4:]),
            }
        )
    return chapter_memory


def build_memory_document(
    *,
    doc_id: str,
    timeline: list[dict[str, Any]],
    current_turn: int,
    current_stage_idx: int,
    current_time_label: str,
) -> dict[str, Any]:
    normalized_timeline = normalize_timeline(timeline)
    chapter_memory = _build_chapter_memory(normalized_timeline)
    session_brief = normalized_timeline[-6:]
    return {
        "version": 1,
        "doc_id": _normalize_doc_id(doc_id),
        "updated_at": _now_iso(),
        "current_turn": int(current_turn),
        "current_stage_idx": int(current_stage_idx),
        "current_time_label": _clean_text(current_time_label),
        "timeline_memory": normalized_timeline,
        "session_brief": session_brief,
        "chapter_memory": chapter_memory,
    }


def prompt_memory_view(document: dict[str, Any] | object, *, current_stage_idx: int) -> dict[str, Any]:
    if not isinstance(document, dict):
        timeline: list[dict[str, Any]] = []
        chapter_memory: list[dict[str, Any]] = []
        session_brief: list[dict[str, Any]] = []
    else:
        timeline = normalize_timeline(document.get("timeline_memory"))
        chapter_memory = document.get("chapter_memory") if isinstance(document.get("chapter_memory"), list) else []
        session_brief = document.get("session_brief") if isinstance(document.get("session_brief"), list) else []

    if not session_brief:
        session_brief = timeline[-6:]

    current_arc = [entry for entry in timeline if int(entry.get("stage_idx", 0)) == int(current_stage_idx)][-6:]
    if not current_arc:
        current_arc = session_brief[-4:]

    current_chapter_summary: dict[str, Any] = {}
    for item in chapter_memory:
        if isinstance(item, dict) and int(item.get("stage_idx", -1)) == int(current_stage_idx):
            current_chapter_summary = item
            break

    return {
        "story_so_far": session_brief,
        "current_arc": current_arc,
        "chapter_memory": current_chapter_summary,
    }


class StoryMemoryStore:
    def __init__(self, base_dir: Path, doc_id: str):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.doc_id = _normalize_doc_id(doc_id)

    def bind(self, doc_id: str) -> str:
        self.doc_id = _normalize_doc_id(doc_id)
        return self.doc_id

    def path_for(self, doc_id: str | None = None) -> Path:
        target = _normalize_doc_id(doc_id or self.doc_id)
        return self.base_dir / f"{target}.json"

    def load(self, doc_id: str | None = None) -> dict[str, Any] | None:
        path = self.path_for(doc_id)
        if not path.exists():
            return None
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    def write(self, document: dict[str, Any], doc_id: str | None = None) -> Path:
        path = self.path_for(doc_id)
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
        return path