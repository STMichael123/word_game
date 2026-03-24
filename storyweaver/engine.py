from __future__ import annotations

import json
import random
import re
from difflib import SequenceMatcher
from dataclasses import asdict
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from dotenv import load_dotenv

from .combat import run_auto_combat, spawn_enemy
from .config import load_settings
from .consistency import enforce_state_invariants, record_fact
from .llm_client import build_client, probe_connection
from .memory_store import StoryMemoryStore, build_memory_document, normalize_timeline, prompt_memory_view
from .nlu import classify_intent_detailed, extract_target_detailed
from .parser import parse_llm_turn
from .quests import (
    ENDING_PATH_HINT,
    FINAL_GOAL_SUMMARY,
    MAIN_STORY,
    PLAYER_OPENING_STANCE,
    SIDE_QUESTS,
    STORY_BACKGROUND,
    stage_by_index,
)
from .state import GameState
from .types import Intent, TurnResult
from .world import LOCATIONS, random_encounter, random_loot, random_location, travel_options


SYSTEM_PROMPT = """你是一位沉浸式武侠小说作者，正在续写一部由玩家选择驱动的江湖传奇。
你必须结合输入中的故事记忆、NPC记忆、已知事实与章节目标，写出连贯且可追溯的下一回。
sim_result 是本回合已经发生的硬结果，必须视为事实基线，叙事不得改写或跳过这些结果。
story_outline_summary、final_goal_summary、current_chapter_arc 是整部故事的固定骨架，只能在其范围内演绎细节，不能擅自改写主线走向。
story_so_far 与 story_memory_current_arc 中的 memory_timestamp 与 memory_index 是按时间顺序整理过的压缩记忆索引，必须据此承接前文，不能把不同时间点的事件写乱。

输出必须是严格 json（JSON 对象）:
{
    "narration": "180~320字，承接上文，有场景、人物动作、冲突推进，且必须解释本回合结果如何发生",
    "memory_summary": "12~28字，作为该回合的记忆索引，只概括最关键推进，不要重复时间信息",
    "options": [
        {"id":"o1","text":"...", "intent":"explore|combat|query|negotiate|travel|rest|use_item", "target":null, "risk":"low|medium|high"},
        {"id":"o2","text":"...", "intent":"...", "target":null, "risk":"..."}
    ]
}

硬性规则：
1) options 数量 2~4。
2) 叙事必须承接 story_so_far，禁止与 known_facts 冲突。
3) 若 npcs_known 中人物再次出现，要体现记忆延续（态度/关系/旧事）。
4) 选项必须指向不同后果，禁止同义改写。
5) 语言保持武侠气质，不使用现代互联网口语。
6) narration 必须优先吸收 sim_result.detail_lines 的信息；若行动失败，要明确写出失败原因，不得强行写成推进成功。
7) options 的 intent 必须来自 allowed_intents。
8) memory_summary 必须简洁、具体，不能照抄 narration 原句，也不能写成空泛套话；时间信息由系统单独记录，不要再写入 memory_summary。
"""


class GameEngine:
    def __init__(self):
        load_dotenv()
        self.settings = load_settings()
        self.rng = random.Random(self.settings.story_seed)
        self.client = build_client(
            base_url=self.settings.base_url,
            api_key=self.settings.llm_api_key,
            model=self.settings.model,
            temperature=self.settings.temperature,
            top_p=self.settings.top_p,
            max_tokens=self.settings.max_tokens,
        )
        self.save_dir = Path("savegames")
        self.save_dir.mkdir(parents=True, exist_ok=True)
        self.memory_store = StoryMemoryStore(self.save_dir / "memory_docs", f"runtime_{uuid4().hex}")
        self.memory_doc_id = self.memory_store.doc_id
        self._memory_doc: dict[str, Any] = {}
        self.state = self._new_state()
        self._normalize_runtime_state()
        self._sync_memory_document()

    def _new_state(self) -> GameState:
        st = GameState(location=random_location(self.rng))
        st.flags["progress"] = 0
        st.flags["stage_idx"] = 0
        st.flags["turn"] = 0
        st.flags["time_phase"] = "白昼"
        st.flags["stage_enter_turn"] = 0
        st.flags["game_over"] = False
        st.flags["game_over_reason"] = ""
        st.flags["game_over_epilogue"] = ""
        st.flags["story_memory"] = []
        st.flags["story_narrations"] = []
        st.flags["story_narrations_recent"] = []
        st.flags["story_narrations_archive"] = []
        st.flags["npc_registry"] = {}
        st.flags["fact_events"] = []
        st.flags["objective_counters"] = {
            "query_count": 0,
            "combat_win": 0,
            "negotiate_win": 0,
            "explore_count": 0,
        }
        st.flags["llm_parse_fail_count"] = 0
        st.flags["last_llm_mode"] = "init"
        st.flags["last_llm_error"] = ""
        st.flags["opening_briefing_shown"] = False
        st.flags["final_goal_shown"] = False
        st.flags["chapter_intro_shown_idx"] = -1
        st.flags["pending_stage_intro_idx"] = 0
        st.flags["active_side_quests"] = []
        st.flags["done_side_quests"] = []
        st.flags["boss_fight"] = {
            "active": False,
            "name": "天门宗师·夜无锋",
            "hp": 0,
            "max_hp": 0,
            "phase": 1,
            "turn": 0,
            "rage": 0,
            "next_move": "未显",
            "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
            "last_log": [],
            "won": False,
        }
        st.flags["skirmish_fight"] = {
            "active": False,
            "name": "",
            "hp": 0,
            "max_hp": 0,
            "atk": 0,
            "defense": 0,
            "style": "",
            "faction": "",
            "origin": "",
            "clue_text": "",
            "clue_fact_key": "",
            "clue_fact_value": "",
            "evidence_item": "",
            "turn": 0,
            "rage": 0,
            "next_move": "未显",
            "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
            "last_log": [],
            "reward_silver": 0,
            "reward_rep": 0,
            "loot": [],
            "won": False,
        }
        st.push_event("system", "江湖初启，你踏入风云之地。", {"loc": st.location})
        return st

    def reset(self) -> None:
        self.state = self._new_state()
        self._normalize_runtime_state()
        self._sync_memory_document()

    def llm_status(self, *, probe: bool = False) -> dict[str, Any]:
        status = {
            "configured": bool(self.settings.llm_api_key),
            "provider": self.settings.provider_hint,
            "base_url": self.settings.base_url,
            "model": self.settings.model,
            "last_mode": str(self.state.flags.get("last_llm_mode", "init")),
            "last_error": str(self.state.flags.get("last_llm_error", "")),
        }
        if probe:
            status.update(
                probe_connection(
                    base_url=self.settings.base_url,
                    api_key=self.settings.llm_api_key,
                    model=self.settings.model,
                )
            )
        else:
            status["ok"] = status["last_mode"] == "online"
        return status

    def _ensure_story_memory(self) -> list[dict[str, Any]]:
        raw = self.state.flags.get("story_memory")
        if isinstance(raw, list):
            return raw
        self.state.flags["story_memory"] = []
        return self.state.flags["story_memory"]

    def _normalize_runtime_state(self) -> None:
        self.state.flags.setdefault("time_phase", "白昼")
        self.state.flags.setdefault("story_memory", [])
        self.state.flags["memory_doc_id"] = self.memory_doc_id
        self._ensure_story_memory()
        self._ensure_story_narrations()
        self._ensure_story_archive()
        self._ensure_npc_registry()
        self._ensure_fact_events()

    def _memory_timeline(self) -> list[dict[str, Any]]:
        return normalize_timeline(self._ensure_story_memory())

    def _rebuild_memory_document(self, timeline: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
        return build_memory_document(
            doc_id=self.memory_doc_id,
            timeline=timeline if timeline is not None else self._memory_timeline(),
            current_turn=int(self.state.flags.get("turn", 0)),
            current_stage_idx=int(self.state.flags.get("stage_idx", 0)),
            current_time_label=self._time_label(),
        )

    def _apply_memory_document(self, document: Optional[dict[str, Any]]) -> None:
        timeline = normalize_timeline(document.get("timeline_memory") if isinstance(document, dict) else [])
        self.state.flags["story_memory"] = timeline
        self.state.flags["memory_doc_id"] = self.memory_doc_id
        self._memory_doc = self._rebuild_memory_document(timeline)

    def _sync_memory_document(self) -> None:
        self._normalize_runtime_state()
        self._memory_doc = self._rebuild_memory_document()
        self.memory_store.write(self._memory_doc)

    def bind_memory_namespace(self, namespace: str) -> None:
        bound = self.memory_store.bind(namespace)
        if bound == self.memory_doc_id and self._memory_doc:
            return
        self.memory_doc_id = bound
        self.state.flags["memory_doc_id"] = self.memory_doc_id
        loaded = self.memory_store.load()
        if loaded is None:
            self._sync_memory_document()
            return
        self._apply_memory_document(loaded)
        self.memory_store.write(self._memory_doc)

    def memory_document(self) -> dict[str, Any]:
        if not self._memory_doc:
            self._sync_memory_document()
        return json.loads(json.dumps(self._memory_doc, ensure_ascii=False))

    def memory_preview(self, limit: int = 5) -> list[dict[str, Any]]:
        view = prompt_memory_view(self._memory_doc, current_stage_idx=int(self.state.flags.get("stage_idx", 0)))
        preview = view.get("story_so_far") if isinstance(view.get("story_so_far"), list) else []
        return preview[-limit:]

    def memory_doc_path(self) -> str:
        return str(self.memory_store.path_for())

    def _ensure_story_narrations(self) -> list[str]:
        raw = self.state.flags.get("story_narrations_recent")
        if isinstance(raw, list):
            return raw

        legacy = self.state.flags.get("story_narrations")
        if isinstance(legacy, list):
            self.state.flags["story_narrations_recent"] = legacy[-20:]
            return self.state.flags["story_narrations_recent"]

        self.state.flags["story_narrations_recent"] = []
        return self.state.flags["story_narrations_recent"]

    def _ensure_story_archive(self) -> list[str]:
        raw = self.state.flags.get("story_narrations_archive")
        if isinstance(raw, list):
            return raw
        self.state.flags["story_narrations_archive"] = []
        return self.state.flags["story_narrations_archive"]

    def _ensure_npc_registry(self) -> dict[str, dict[str, Any]]:
        raw = self.state.flags.get("npc_registry")
        if isinstance(raw, dict):
            return raw
        self.state.flags["npc_registry"] = {}
        return self.state.flags["npc_registry"]

    def _ensure_fact_events(self) -> list[dict[str, Any]]:
        raw = self.state.flags.get("fact_events")
        if isinstance(raw, list):
            return raw
        self.state.flags["fact_events"] = []
        return self.state.flags["fact_events"]

    def _ensure_objective_counters(self) -> dict[str, int]:
        raw = self.state.flags.get("objective_counters")
        if isinstance(raw, dict):
            return {
                "query_count": int(raw.get("query_count", 0)),
                "combat_win": int(raw.get("combat_win", 0)),
                "negotiate_win": int(raw.get("negotiate_win", 0)),
                "explore_count": int(raw.get("explore_count", 0)),
            }
        return {
            "query_count": 0,
            "combat_win": 0,
            "negotiate_win": 0,
            "explore_count": 0,
        }

    def _is_stage_goal_met(self, stage_idx: int, counters: dict[str, int], st: GameState) -> bool:
        stage = stage_by_index(stage_idx)
        if not stage:
            return False

        for key, need in stage.goal_counters.items():
            if int(counters.get(key, 0)) < int(need):
                return False

        for fact in stage.required_facts:
            if not bool(st.known_facts.get(fact)):
                return False

        return True

    def _get_stage_timing(self) -> dict[str, int]:
        st = self.state
        idx = int(st.flags.get("stage_idx", 0))
        stage = stage_by_index(idx)
        if not stage:
            return {"estimated": 0, "limit": 0, "elapsed": 0, "remaining": 0}
        enter_turn = int(st.flags.get("stage_enter_turn", 0))
        turn = int(st.flags.get("turn", 0))
        elapsed = max(0, turn - enter_turn)
        limit = int(stage.fail_turn_budget)
        return {
            "estimated": int(stage.estimated_turns),
            "limit": limit,
            "elapsed": elapsed,
            "remaining": max(0, limit - elapsed),
        }

    def _time_phase(self) -> str:
        phase = str(self.state.flags.get("time_phase", "白昼") or "白昼")
        return phase if phase in {"白昼", "夜幕"} else "白昼"

    def _time_label(self) -> str:
        return f"第{self.state.day}日·{self._time_phase()}"

    def _memory_timestamp(self) -> str:
        phase = "上午" if self._time_phase() == "白昼" else "下午"
        return f"第{self.state.day}日{phase}"

    def _time_event_note(self) -> tuple[str, str]:
        stage = stage_by_index(int(self.state.flags.get("stage_idx", 0)))
        if self._time_phase() == "夜幕":
            note = self.rng.choice(
                [
                    f"夜幕落下后，{self.state.location}的耳目与埋伏都比白日更活跃。",
                    "夜色把真话与杀机一起放大，任何试探都更容易惊动暗处的人。",
                    "灯火渐疏之后，江湖中真正敢露面的，多半都不是善客。",
                ]
            )
            significance = "夜间更适合埋伏、交易和灭口，局势会比白日更险。"
        else:
            note = self.rng.choice(
                [
                    f"东方既白，{self.state.location}的人情往来重新浮到明面上。",
                    "日色一亮，许多昨夜藏住的痕迹都开始变得可供追查。",
                    "白日之下，市井流言、镖路动静与人心试探都更容易显形。",
                ]
            )
            significance = "白昼更适合观察人情、追索痕迹和公开打探，消息会更清楚。"
        if stage:
            significance = f"{significance} 这和本章“{stage.objective}”直接相关。"
        return note, significance

    def _advance_world_time(self) -> list[str]:
        st = self.state
        previous_phase = self._time_phase()
        next_phase = "夜幕" if previous_phase == "白昼" else "白昼"
        if previous_phase == "夜幕":
            st.day += 1
        st.flags["time_phase"] = next_phase
        note, significance = self._time_event_note()
        self._append_fact_event(
            event_type="time_event",
            summary=note,
            significance=significance,
            refs=[self._time_label(), st.location],
        )
        return [f"时序推进到{self._time_label()}。", note]

    def _build_game_over_turn(self, reason: str) -> TurnResult:
        epilogue = str(self.state.flags.get("game_over_epilogue") or "").strip()
        if not epilogue:
            epilogue = "你在错综局势中错失了最后的窗口，江湖风向彻底逆转。"
        return {
            "narration": f"你在当前章节拖延太久：{reason}\n本局失败。{epilogue}\n请输入 /reset 重开新档。",
            "options": [
                {"id": "g1", "text": "/reset", "intent": "unknown", "target": None, "risk": "low"},
            ],
            "debug": {"game_over": True, "reason": reason},
        }
    def _generate_failure_epilogue(self, reason: str) -> str:
        st = self.state
        idx = int(st.flags.get("stage_idx", 0))
        stage = stage_by_index(idx)
        stage_title = stage.title if stage else "无名章节"
        recent = self._ensure_story_memory()[-3:]
        recent_text = "\n".join(f"- {x.get('summary', '')}" for x in recent if isinstance(x, dict))
        prompt_payload = {
            "stage": stage_title,
            "reason": reason,
            "recent": recent_text,
            "instruction": "写一段80~140字的武侠失败结局，必须有余韵，不要给选项。",
        }
        try:
            resp = self.client.chat(
                [
                    {"role": "system", "content": "你是武侠小说作者，产出简洁失败结局段落。"},
                    {"role": "user", "content": json.dumps(prompt_payload, ensure_ascii=False)},
                ]
            )
            parsed, _ = parse_llm_turn(resp)
            if parsed and parsed.narration.strip():
                return parsed.narration.strip()
            txt = str(resp or "").strip()
            if txt:
                return txt[:220]
        except Exception:
            pass
        return "你回望来路，方知一步迟缓便是满盘皆输。此役虽败，江湖仍留你再起的火种。"

    def _check_stage_timeout(self) -> Optional[TurnResult]:
        st = self.state
        if bool(st.flags.get("game_over")):
            return self._build_game_over_turn(str(st.flags.get("game_over_reason") or "章节失败"))

        idx = int(st.flags.get("stage_idx", 0))
        stage = stage_by_index(idx)
        if not stage:
            return None

        timing = self._get_stage_timing()
        if timing["limit"] > 0 and timing["elapsed"] > timing["limit"]:
            reason = f"{stage.title} 超过时限 {timing['limit']} 回合"
            st.flags["game_over"] = True
            st.flags["game_over_reason"] = reason
            st.flags["game_over_epilogue"] = self._generate_failure_epilogue(reason)
            st.push_event("game_over", reason, {"stage": stage.id, "elapsed": timing["elapsed"]})
            turn = self._build_game_over_turn(reason)
            st.last_options = turn["options"]
            return turn

        return None

    @staticmethod
    def _chapter_hook(stage_idx: int) -> str:
        hooks = [
            "初入江湖，试探人心与门路。",
            "线索分岔，真假消息混入市井。",
            "旧案牵出新敌，局势转向暗斗。",
            "同盟与背叛并行，信任成本骤升。",
            "关键证据浮现，各方开始抢先落子。",
            "真相边缘已现，必须在风险中前行。",
            "终章前夜，所有伏笔开始回收。",
            "天门将启，抉择会重写江湖秩序。",
        ]
        if 0 <= stage_idx < len(hooks):
            return hooks[stage_idx]
        return "终局之后，余波仍在江湖扩散。"

    @staticmethod
    def _story_outline_summary() -> str:
        return f"{STORY_BACKGROUND} {PLAYER_OPENING_STANCE} {FINAL_GOAL_SUMMARY} {ENDING_PATH_HINT}"

    def _chapter_intro_text(self, stage_idx: int) -> str:
        stage = stage_by_index(stage_idx)
        if not stage:
            return "【终局之后】你已走过全局风波，江湖余波仍在等待你回望。"
        return (
            f"【第{stage_idx + 1}章·{stage.title}】{stage.chapter_intro}\n"
            f"本章冲突：{stage.chapter_conflict}\n"
            f"本章要务：{stage.objective}\n"
            f"这一章的重要性：{stage.chapter_significance}"
        )

    def opening_scene(self) -> TurnResult:
        st = self.state
        stage = stage_by_index(int(st.flags.get("stage_idx", 0)))
        options = [
            {"id": "o1", "text": "先在镇中打听黑松会的风声", "intent": "query", "target": None, "risk": "low"},
            {"id": "o2", "text": "沿街市与客栈观察可疑人物", "intent": "explore", "target": None, "risk": "medium"},
            {"id": "o3", "text": "拜访愿意开口的店家与旅人", "intent": "negotiate", "target": None, "risk": "low"},
        ]
        st.last_options = options
        st.flags["opening_briefing_shown"] = True
        st.flags["final_goal_shown"] = True
        st.flags["chapter_intro_shown_idx"] = int(st.flags.get("stage_idx", 0))
        st.flags["pending_stage_intro_idx"] = -1
        intro = self._chapter_intro_text(int(st.flags.get("stage_idx", 0))) if stage else ""
        return {
            "narration": "你踏入青石镇的这一刻，就已经被卷进一场从市井延向天门旧局的风暴。江湖不会先替你解释一切，但你必须尽快看懂局势。",
            "options": options,
            "debug": {"opening": True},
            "system_messages": [
                f"【江湖背景】{STORY_BACKGROUND}",
                f"【你的来路】{PLAYER_OPENING_STANCE}",
                f"【终局目标】{FINAL_GOAL_SUMMARY} {ENDING_PATH_HINT}",
                intro,
            ],
        }

    def _consume_pending_chapter_intro(self) -> list[str]:
        st = self.state
        pending_idx = int(st.flags.get("pending_stage_intro_idx", -1))
        shown_idx = int(st.flags.get("chapter_intro_shown_idx", -1))
        if pending_idx < 0 or pending_idx == shown_idx:
            return []
        st.flags["chapter_intro_shown_idx"] = pending_idx
        st.flags["pending_stage_intro_idx"] = -1
        return [self._chapter_intro_text(pending_idx)]

    @staticmethod
    def _narrative_tone(st: GameState) -> str:
        if st.health <= 35:
            return "伤势沉重，行文应带危机与谨慎感。"
        if st.stamina <= 25:
            return "体力见底，行文应强调取舍与节奏。"
        if st.reputation >= 45:
            return "名望已高，行文可体现江湖回应与人情压力。"
        return "风云未定，行文保持探索与悬念。"

    @staticmethod
    def _delta_summary(delta: dict[str, int]) -> str:
        parts: list[str] = []
        labels = {
            "health": "气血",
            "stamina": "体力",
            "silver": "银两",
            "reputation": "声望",
            "progress": "进度",
        }
        for key in ("health", "stamina", "silver", "reputation", "progress"):
            val = int(delta.get(key, 0))
            if val == 0:
                continue
            sign = "+" if val > 0 else ""
            parts.append(f"{labels[key]}{sign}{val}")
        return "，".join(parts) if parts else "无明显变化"

    @staticmethod
    def _clean_story_note(text: str) -> str:
        txt = str(text or "").strip()
        if txt.startswith("【") and "】" in txt:
            txt = txt.split("】", 1)[1].strip()
        return txt.rstrip("。！？!? ")

    def _normalize_memory_index(self, text: str) -> str:
        txt = self._clean_story_note(text)
        txt = re.sub(r"^第\d+日(?:上午|下午)[，,:：\s]*", "", txt)
        txt = re.sub(r"^第\d+日·(?:白昼|夜幕)[，,:：\s]*", "", txt)
        txt = re.sub(r"\s+", " ", txt).strip(" ，,;；")
        return txt[:32]

    def _build_memory_index(
        self,
        *,
        action: str,
        sim_result: dict[str, Any],
        stage_notes: list[str],
        memory_summary: str = "",
    ) -> str:
        detail_lines = sim_result.get("detail_lines") if isinstance(sim_result.get("detail_lines"), list) else []
        candidates = [memory_summary]
        candidates.extend(str(line) for line in detail_lines[:3])
        candidates.extend(stage_notes[:2])
        if action:
            candidates.append(f"你执行了{self._clean_story_note(action)}")

        for candidate in candidates:
            index = self._normalize_memory_index(candidate)
            if index:
                return index

        stage = stage_by_index(int(self.state.flags.get("stage_idx", 0)))
        if stage:
            return self._normalize_memory_index(f"围绕{stage.objective}继续试探")
        return "谨慎推进局势"

    @staticmethod
    def _story_memory_prompt_entry(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "turn": int(item.get("turn", 0)),
            "stage_idx": int(item.get("stage_idx", 0)),
            "stage_title": str(item.get("stage_title", "")).strip(),
            "memory_timestamp": str(item.get("memory_timestamp") or item.get("time_label") or "").strip(),
            "memory_index": str(item.get("memory_index") or item.get("summary") or "").strip(),
            "chapter_goal_effect": str(item.get("chapter_goal_effect", "")).strip(),
            "location": str(item.get("location", "")).strip(),
        }

    def _compress_story_memory_for_prompt(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compressed: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            entry = self._story_memory_prompt_entry(item)
            if entry["memory_timestamp"] or entry["memory_index"]:
                compressed.append(entry)
        return compressed

    @staticmethod
    def _fact_label(key: str) -> str:
        mapping = {
            "black_wood_token": "黑木令牌",
            "escort_token": "镖局信物",
            "black_pine_activity": "黑松会活动痕迹",
            "escort_guild_infiltrated": "镖局内鬼迹象",
        }
        return mapping.get(key, key)

    @staticmethod
    def _extract_npc_names(text: str) -> list[str]:
        if not text:
            return []
        names: list[str] = []
        names.extend(re.findall(r"[\u4e00-\u9fff]{1,4}·[\u4e00-\u9fff]{1,4}", text))
        names.extend(
            re.findall(
                r"(?:掌柜|店小二|镖师|剑客|刀客|医女|道人|公子|姑娘|长老|堂主|护法|捕头|仵作)[\u4e00-\u9fff]{1,3}",
                text,
            )
        )
        stop = {"江湖", "终章", "天门", "宗师", "夜无锋", "玩家", "少侠", "侠客", "回合"}
        uniq: list[str] = []
        for name in names:
            if name in stop or name in uniq:
                continue
            uniq.append(name)
        return uniq[:6]

    def _record_story_memory(
        self,
        *,
        action: str,
        narration: str,
        sim_result: dict[str, Any],
        stage_notes: list[str],
        memory_summary: str = "",
    ) -> None:
        st = self.state
        story_memory = self._ensure_story_memory()
        narrations = self._ensure_story_narrations()
        narrations_archive = self._ensure_story_archive()
        npc_registry = self._ensure_npc_registry()
        fact_events = self._ensure_fact_events()
        stage_idx = int(st.flags.get("stage_idx", 0))
        current_stage = stage_by_index(stage_idx)

        detail_lines = sim_result.get("detail_lines")
        details = [self._clean_story_note(str(x)) for x in detail_lines[:3]] if isinstance(detail_lines, list) else []
        clean_stage_notes = [self._clean_story_note(x) for x in stage_notes if self._clean_story_note(x)]
        memory_timestamp = self._memory_timestamp()
        summary = self._build_memory_index(
            action=action,
            sim_result=sim_result,
            stage_notes=clean_stage_notes,
            memory_summary=memory_summary,
        )

        progress_delta = int((sim_result.get("delta") or {}).get("progress", 0)) if isinstance(sim_result.get("delta"), dict) else 0
        if clean_stage_notes:
            story_significance = clean_stage_notes[0]
        elif details:
            story_significance = details[0]
        elif progress_delta > 0 and current_stage:
            story_significance = f"你又向本章目标“{current_stage.objective}”逼近了一步。"
        elif current_stage:
            story_significance = f"这一手暂未真正撬动本章目标“{current_stage.objective}”。"
        else:
            story_significance = "局势仍在缓慢变化。"

        if current_stage:
            chapter_goal_effect = (
                f"这一步直接服务于本章目标：{current_stage.objective}。"
                if progress_delta > 0 or clean_stage_notes
                else f"这一步尚未有效推进本章目标：{current_stage.objective}。"
            )
        else:
            chapter_goal_effect = "终局已近，每一步都会影响最后的抉择。"

        npc_names = self._extract_npc_names((narration or "") + "\n" + (action or ""))
        for npc in npc_names:
            prev = npc_registry.get(npc, {}) if isinstance(npc_registry.get(npc), dict) else {}
            interaction_log = list(prev.get("interactions", [])) if isinstance(prev.get("interactions"), list) else []
            interaction_log.append(
                {
                    "turn": int(st.flags.get("turn", 0)),
                    "stage_idx": stage_idx,
                    "summary": summary[:80],
                }
            )
            npc_registry[npc] = {
                "relation": int(st.relations.get(npc, prev.get("relation", 0))),
                "last_loc": st.location,
                "note": str(prev.get("note") or story_significance or "在江湖传闻中留下了名字"),
                "interactions": interaction_log[-3:],
            }

        fact_refs = [x for x in details[:2] if x]
        if clean_stage_notes:
            fact_refs.extend(clean_stage_notes[:1])
        if npc_names or fact_refs:
            fact_events.append(
                {
                    "turn": int(st.flags.get("turn", 0)),
                    "stage_idx": stage_idx,
                    "time_label": self._time_label(),
                    "location": st.location,
                    "type": "story_turn",
                    "summary": story_significance,
                    "significance": chapter_goal_effect,
                    "npc_refs": npc_names[:4],
                    "fact_refs": fact_refs[:3],
                }
            )

        entry = {
            "turn": int(st.flags.get("turn", 0)),
            "stage_idx": stage_idx,
            "stage_title": current_stage.title if current_stage else "终局",
            "memory_timestamp": memory_timestamp,
            "memory_index": summary,
            "time_label": self._time_label(),
            "day": st.day,
            "time_phase": self._time_phase(),
            "action": action,
            "summary": summary,
            "story_significance": story_significance,
            "chapter_goal_effect": chapter_goal_effect,
            "location": st.location,
            "npcs_met": npc_names,
            "npc_refs": npc_names,
            "fact_refs": fact_refs[:3],
            "delta_summary": self._delta_summary(sim_result.get("delta", {})),
        }
        story_memory.append(entry)
        narrations.append(narration or "")
        narrations_archive.append(narration or "")

        if len(story_memory) > 80:
            st.flags["story_memory"] = story_memory[-80:]
        if len(narrations) > 30:
            st.flags["story_narrations_recent"] = narrations[-30:]
        if len(narrations_archive) > 2000:
            st.flags["story_narrations_archive"] = narrations_archive[-2000:]
        if len(fact_events) > 120:
            st.flags["fact_events"] = fact_events[-120:]
        self._sync_memory_document()

    def save(self, slot: str = "slot1") -> str:
        self._sync_memory_document()
        p = self.save_dir / f"{slot}.json"
        p.write_text(self.state.to_save_json(), encoding="utf-8")
        self.memory_store.write(self._memory_doc, doc_id=slot)
        return str(p)

    def load(self, slot: str = "slot1") -> bool:
        p = self.save_dir / f"{slot}.json"
        if not p.exists():
            return False
        self.state = GameState.from_save_json(p.read_text(encoding="utf-8"))
        self._normalize_runtime_state()
        loaded_memory = self.memory_store.load(slot)
        if loaded_memory is not None:
            self._apply_memory_document(loaded_memory)
        else:
            self._sync_memory_document()
            return True
        self.memory_store.write(self._memory_doc)
        return True

    def _normalize_input(self, user_text: str) -> str:
        t = (user_text or "").strip()
        t = t.replace("【主线建议】", "").strip()
        if t.isdigit() and self.state.last_options:
            idx = int(t) - 1
            if 0 <= idx < len(self.state.last_options):
                picked = str(self.state.last_options[idx].get("text", t))
                return picked.replace("【主线建议】", "").strip()
        return t

    def _match_last_option(self, user_text: str) -> Optional[dict[str, Any]]:
        normalized = self._normalize_input(user_text)
        for opt in self.state.last_options or []:
            text = str(opt.get("text") or "").replace("【主线建议】", "").strip()
            if text and text == normalized:
                return opt
        return None

    def _build_clarification_options(self, intent: Intent) -> list[dict[str, Any]]:
        st = self.state
        options: list[dict[str, Any]] = []

        if intent == Intent.TRAVEL:
            for i, loc in enumerate(travel_options(st.location)[:3], start=1):
                options.append({"id": f"c{i}", "text": f"前往{loc}", "intent": "travel", "target": loc, "risk": "low"})
            return options

        if intent == Intent.NEGOTIATE:
            defaults = ["店小二", "镖师", "药铺掌柜"]
            for i, name in enumerate(defaults, start=1):
                options.append({"id": f"c{i}", "text": f"拜访{name}", "intent": "negotiate", "target": name, "risk": "low"})
            return options

        if intent == Intent.USE_ITEM:
            usable = [x for x in st.inventory if any(k in x for k in ("止血", "回气", "丹", "散", "药", "酒", "膏"))]
            if usable:
                for i, item in enumerate(usable[:3], start=1):
                    options.append({"id": f"c{i}", "text": f"使用{item}", "intent": "use_item", "target": item, "risk": "low"})
            else:
                options = [
                    {"id": "c1", "text": "先查看背包后再决定使用什么", "intent": "inventory", "target": None, "risk": "low"},
                    {"id": "c2", "text": "去药铺打听可用药材", "intent": "query", "target": "药铺", "risk": "low"},
                    {"id": "c3", "text": "暂缓用药，先调息观察伤势", "intent": "rest", "target": None, "risk": "low"},
                ]
            return options

        return [
            {"id": "c1", "text": "继续谨慎探索", "intent": "explore", "target": None, "risk": "low"},
            {"id": "c2", "text": "先向周围人打听", "intent": "query", "target": None, "risk": "low"},
            {"id": "c3", "text": "短暂休整后再行动", "intent": "rest", "target": None, "risk": "low"},
        ]

    def _boss_state(self) -> dict[str, Any]:
        raw = self.state.flags.get("boss_fight")
        if isinstance(raw, dict):
            return raw
        self.state.flags["boss_fight"] = {
            "active": False,
            "name": "天门宗师·夜无锋",
            "hp": 0,
            "max_hp": 0,
            "phase": 1,
            "turn": 0,
            "rage": 0,
            "next_move": "未显",
            "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
            "last_log": [],
            "won": False,
        }
        return self.state.flags["boss_fight"]

    def is_boss_available(self) -> bool:
        st = self.state
        return int(st.flags.get("stage_idx", 0)) >= len(MAIN_STORY) - 1

    def is_boss_active(self) -> bool:
        return bool(self._boss_state().get("active"))

    def _skirmish_state(self) -> dict[str, Any]:
        raw = self.state.flags.get("skirmish_fight")
        if isinstance(raw, dict):
            return raw
        self.state.flags["skirmish_fight"] = {
            "active": False,
            "name": "",
            "hp": 0,
            "max_hp": 0,
            "atk": 0,
            "defense": 0,
            "style": "",
            "faction": "",
            "origin": "",
            "clue_text": "",
            "clue_fact_key": "",
            "clue_fact_value": "",
            "evidence_item": "",
            "turn": 0,
            "rage": 0,
            "next_move": "未显",
            "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
            "last_log": [],
            "reward_silver": 0,
            "reward_rep": 0,
            "loot": [],
            "won": False,
        }
        return self.state.flags["skirmish_fight"]

    def is_skirmish_active(self) -> bool:
        return bool(self._skirmish_state().get("active"))

    def _start_skirmish(self, enemy: Any) -> None:
        sk = self._skirmish_state()
        sk.update(
            {
                "active": True,
                "name": str(enemy.name),
                "hp": int(enemy.hp),
                "max_hp": int(enemy.hp),
                "atk": int(enemy.atk),
                "defense": int(enemy.defense),
                "style": str(enemy.style),
                "faction": str(getattr(enemy, "faction", "江湖散人")),
                "origin": str(getattr(enemy, "origin", "来路未明")),
                "clue_text": str(getattr(enemy, "clue_text", "")),
                "clue_fact_key": str(getattr(enemy, "clue_fact_key", "")),
                "clue_fact_value": str(getattr(enemy, "clue_fact_value", "")),
                "evidence_item": str(getattr(enemy, "evidence_item", "")),
                "turn": 1,
                "rage": 35,
                "next_move": "试探",
                "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
                "last_log": [f"你与【{enemy.name}】狭路相逢，对方出身{getattr(enemy, 'origin', '来路未明')}，路数是{enemy.style}。"],
                "reward_silver": int(enemy.reward_silver),
                "reward_rep": int(enemy.reward_rep),
                "loot": [],
                "won": False,
            }
        )

    def _after_skirmish_options(self) -> list[dict[str, Any]]:
        return [
            {"id": "a1", "text": "检查四周痕迹，看看此战是否牵出新线索", "intent": "explore", "target": None, "risk": "low"},
            {"id": "a2", "text": "向附近人物追问这名对手的来路", "intent": "query", "target": None, "risk": "low"},
            {"id": "a3", "text": "先调息整备，稳住伤势再说", "intent": "rest", "target": None, "risk": "low"},
        ]

    def _remember_known_fact_list(self, key: str, value: str) -> None:
        st = self.state
        raw = st.known_facts.get(key)
        items = list(raw) if isinstance(raw, list) else []
        if value and value not in items:
            items.append(value)
        record_fact(st, key, items)

    def _append_fact_event(
        self,
        *,
        event_type: str,
        summary: str,
        significance: str,
        refs: Optional[list[str]] = None,
    ) -> None:
        events = self._ensure_fact_events()
        events.append(
            {
                "turn": int(self.state.flags.get("turn", 0)),
                "stage_idx": int(self.state.flags.get("stage_idx", 0)),
                "location": self.state.location,
                "type": event_type,
                "summary": self._clean_story_note(summary),
                "significance": self._clean_story_note(significance),
                "refs": [x for x in (refs or []) if x][:4],
            }
        )

    def _record_skirmish_facts(self, *, enemy_state: dict[str, Any], won: bool) -> list[str]:
        st = self.state
        notes: list[str] = []
        name = str(enemy_state.get("name") or "").strip()
        faction = str(enemy_state.get("faction") or "").strip()
        origin = str(enemy_state.get("origin") or "").strip()
        clue_text = str(enemy_state.get("clue_text") or "").strip()
        clue_fact_key = str(enemy_state.get("clue_fact_key") or "").strip()
        clue_fact_value = str(enemy_state.get("clue_fact_value") or "").strip()
        evidence_item = str(enemy_state.get("evidence_item") or "").strip()

        if name:
            self._remember_known_fact_list("enemy_names_seen", name)
        if faction:
            self._remember_known_fact_list("enemy_factions_seen", faction)
            notes.append(f"你辨认出此人属于{faction}。")
            if faction == "黑松会":
                record_fact(st, "black_pine_activity", True)
                self._append_fact_event(
                    event_type="faction_reveal",
                    summary=f"你确认眼前敌手属于{faction}。",
                    significance="这说明黑松会已经把触角伸进当前章节的冲突核心。",
                    refs=[name, faction, origin],
                )
        if origin:
            self._remember_known_fact_list("enemy_origins_seen", origin)

        if won and clue_text:
            self._remember_known_fact_list("combat_clues", clue_text)
            notes.append(clue_text)
            self._append_fact_event(
                event_type="combat_clue",
                summary=clue_text,
                significance="战后掉出的线索把这场遭遇战和主线调查重新连到了一起。",
                refs=[name, faction, origin],
            )
        if won and clue_fact_key:
            normalized_value: Any = clue_fact_value
            if clue_fact_value == "True":
                normalized_value = True
            record_fact(st, clue_fact_key, normalized_value)
            self._append_fact_event(
                event_type="fact_unlock",
                summary=f"你确认了关键事实：{self._fact_label(clue_fact_key)}。",
                significance="这类硬事实会决定后续章节的判断方向。",
                refs=[self._fact_label(clue_fact_key)],
            )
        if won and evidence_item:
            if evidence_item not in st.inventory:
                st.inventory.append(evidence_item)
            self._remember_known_fact_list("combat_evidence", evidence_item)
            notes.append(f"你从对手身上搜出证物：{evidence_item}。")
            if evidence_item == "镖局信物":
                record_fact(st, "escort_token", True)
            if evidence_item == "黑木令牌":
                record_fact(st, "black_wood_token", True)
            self._append_fact_event(
                event_type="evidence",
                summary=f"你夺得关键证物：{evidence_item}。",
                significance="证物不仅能证明敌手来路，也会在后续谈判和指认中成为筹码。",
                refs=[evidence_item, name, faction],
            )
        return notes

    def _chapter_progress_narrative(self, stage_idx: int) -> str:
        stage = stage_by_index(stage_idx)
        if not stage:
            return "你已站在终局边缘，接下来每一步都将直接指向最后的抉择。"

        counters = self._ensure_objective_counters()
        counter_labels = {
            "query_count": "情报打听",
            "combat_win": "取胜战斗",
            "negotiate_win": "谈判突破",
            "explore_count": "实地探索",
        }
        progress_bits: list[str] = []
        for key, need in stage.goal_counters.items():
            progress_bits.append(f"{counter_labels.get(key, key)} {int(counters.get(key, 0))}/{int(need)}")

        missing_facts = [self._fact_label(x) for x in stage.required_facts if not bool(self.state.known_facts.get(x))]
        timing = self._get_stage_timing()
        parts = [f"当前时间是{self._time_label()}。本章目标是：{stage.objective}。"]
        if progress_bits:
            parts.append("当前关键进度：" + "；".join(progress_bits) + "。")
        if missing_facts:
            parts.append("仍未拿到的关键事实/证物：" + "、".join(missing_facts) + "。")
        if int(timing.get("remaining", 0)) > 0:
            parts.append(f"本章剩余大约 {int(timing.get('remaining', 0))} 回合缓冲，不能继续在同一类动作上空转。")
        return "".join(parts)

    def _recent_fact_timeline(self) -> list[str]:
        timeline: list[str] = []
        for event in self._ensure_fact_events()[-6:]:
            if not isinstance(event, dict):
                continue
            turn = int(event.get("turn", 0))
            time_label = str(event.get("time_label", "")).strip()
            summary = self._clean_story_note(event.get("summary", ""))
            significance = self._clean_story_note(event.get("significance", ""))
            if not summary:
                continue
            prefix = f"{time_label} 第{turn}回：" if time_label else f"第{turn}回："
            if significance:
                timeline.append(f"{prefix}{summary} 这意味着{significance}")
            else:
                timeline.append(f"{prefix}{summary}")
        return timeline

    def _story_memory_current_arc(self, story_so_far: list[dict[str, Any]]) -> list[dict[str, Any]]:
        current_idx = int(self.state.flags.get("stage_idx", 0))
        current = [x for x in story_so_far if isinstance(x, dict) and int(x.get("stage_idx", current_idx)) == current_idx]
        return current[-4:] if current else story_so_far[-4:]

    def _fallback_memory_summary(self, action: str, sim_result: dict[str, Any], stage_notes: list[str]) -> str:
        return self._build_memory_index(
            action=action,
            sim_result=sim_result,
            stage_notes=stage_notes,
        )

    def _narration_too_similar(self, narration: str) -> bool:
        candidate = str(narration or "").strip()
        if not candidate:
            return False
        for recent in self._ensure_story_narrations()[-3:]:
            text = str(recent or "").strip()
            if not text:
                continue
            if SequenceMatcher(None, candidate, text).ratio() >= 0.74:
                return True
        return False

    def skirmish_skill_action(self, skill: str) -> TurnResult:
        sk = self._skirmish_state()
        if not sk.get("active"):
            return {
                "narration": "当前并无遭遇战，你可以先通过行动触发新的江湖冲突。",
                "options": self.state.last_options or [],
                "debug": {"skirmish": "inactive"},
            }

        st = self.state
        prev_health = st.health
        prev_stamina = st.stamina
        prev_silver = st.silver
        prev_reputation = st.reputation
        prev_progress = int(st.flags.get("progress", 0))
        cds: dict[str, int] = sk["cooldowns"]
        sk_map = {"轻功": "qg", "招架": "zg", "内功": "ng", "绝技": "jj"}
        sk_key = sk_map.get(skill, "")
        logs: list[str] = []

        for key in cds:
            cds[key] = max(0, int(cds[key]) - 1)

        enemy_def = int(sk.get("defense", 0))
        if sk_key == "" or cds.get(sk_key, 0) > 0:
            player_damage = max(4, 6 + st.martial_level + self.rng.randint(0, 4) - enemy_def // 3)
            stamina_cost = 5
            logs.append("你仓促应招，招式未尽其妙。")
        elif sk_key == "qg":
            player_damage = max(8, 11 + st.martial_level * 2 + self.rng.randint(1, 7) - enemy_def // 2)
            stamina_cost = 9
            cds["qg"] = 1
            logs.append("你提气纵身，步法斜切敌侧，剑光如燕。")
        elif sk_key == "zg":
            player_damage = max(6, 8 + st.martial_level + self.rng.randint(1, 5) - enemy_def // 2)
            stamina_cost = 7
            cds["zg"] = 1
            st.flags["skirmish_guard_buff"] = 1
            logs.append("你沉臂守中，借对手劲力反震回去。")
        elif sk_key == "ng":
            player_damage = max(12, 13 + st.inner_power // 10 + self.rng.randint(2, 9) - enemy_def // 3)
            stamina_cost = 13
            cds["ng"] = 2
            logs.append("你运转内息，劲力透刃而出，直逼对手要害。")
        else:
            stamina_cost = 20
            if int(sk.get("rage", 0)) < 100:
                player_damage = max(7, 9 + st.martial_level + self.rng.randint(1, 5) - enemy_def // 3)
                stamina_cost = 10
                logs.append("绝技火候未足，你只得强催一记重手。")
            else:
                player_damage = max(18, 18 + st.martial_level * 3 + self.rng.randint(4, 10) - enemy_def // 4)
                cds["jj"] = 3
                sk["rage"] = 0
                logs.append("你一式绝技轰然出手，杀势如开碑裂石。")

        if st.stamina < stamina_cost:
            player_damage = max(3, player_damage // 2)
            logs.append("你气力不足，这一击的威势被削去了大半。")
        st.stamina = max(0, st.stamina - stamina_cost)
        sk["hp"] = max(0, int(sk["hp"]) - player_damage)
        sk["rage"] = min(100, int(sk.get("rage", 0)) + 12 + (4 if sk_key == "qg" else 0) + (5 if sk_key == "zg" else 0))
        logs.append(f"你对{sk.get('name')}造成 {player_damage} 点伤害。")

        if int(sk["hp"]) <= 0:
            reward_silver = int(sk.get("reward_silver", 0))
            reward_rep = int(sk.get("reward_rep", 0))
            st.silver += reward_silver
            st.reputation += reward_rep
            st.flags["progress"] = int(st.flags.get("progress", 0)) + 3
            counters = st.flags.get("objective_counters")
            if isinstance(counters, dict):
                counters["combat_win"] = int(counters.get("combat_win", 0)) + 1
            loot: list[str] = []
            if self.rng.random() < 0.28:
                loot.append("血纹刀穗")
                st.inventory.append("血纹刀穗")
            sk["active"] = False
            sk["won"] = True
            sk["loot"] = loot
            fact_notes = self._record_skirmish_facts(enemy_state=sk, won=True)
            sim_result = {
                "delta": {
                    "health": st.health - prev_health,
                    "stamina": st.stamina - prev_stamina,
                    "silver": st.silver - prev_silver,
                    "reputation": st.reputation - prev_reputation,
                    "progress": int(st.flags.get("progress", 0)) - prev_progress,
                },
                "detail_lines": [
                    f"你在遭遇战中击败了{sk.get('name')}。",
                    *logs,
                    *([f"你获得战利品：{loot[0]}。"] if loot else []),
                    *fact_notes,
                ],
                "encounter": {
                    "kind": "combat",
                    "name": sk.get("name"),
                    "style": sk.get("style"),
                    "faction": sk.get("faction"),
                    "origin": sk.get("origin"),
                },
                "intent_outcomes": {"combat_won": True, "negotiate_won": False, "target": sk.get("name")},
            }
            stage_notes = self._update_story_stage(Intent.COMBAT, sim_result)
            sk["last_log"] = logs
            st.push_event("skirmish", "击败遭遇敌手", {"name": sk.get("name")})
            turn = self._generate_story_turn(
                action=f"在遭遇战中使出{skill}并取胜",
                sim_result=sim_result,
                stage_notes=stage_notes,
            )
            turn["debug"]["skirmish"] = "won"
            return turn

        move_pool = ["扑身急斩", "翻腕连挑", "贴身抢攻", "拖刀反掠"]
        move = self.rng.choice(move_pool)
        next_pred = self.rng.choice(move_pool)
        sk["next_move"] = next_pred
        enemy_atk = int(sk.get("atk", 0))
        guard_bonus = 5 if st.flags.pop("skirmish_guard_buff", 0) else 0
        enemy_damage = max(1, enemy_atk + self.rng.randint(0, 5) - (st.martial_level + guard_bonus))
        st.health = max(0, st.health - enemy_damage)
        logs.append(f"{sk.get('name')}使出【{move}】，你受到 {enemy_damage} 点伤害。")
        logs.append(f"你看出对方下一招气机微露：{next_pred}。")

        if st.health == 0:
            st.health = max(10, st.max_health // 6)
            st.stamina = max(8, st.max_stamina // 7)
            sk["active"] = False
            sk["last_log"] = logs + ["你强行撤出战圈，暂且保住性命。"]
            sim_result = {
                "delta": {
                    "health": st.health - prev_health,
                    "stamina": st.stamina - prev_stamina,
                    "silver": st.silver - prev_silver,
                    "reputation": st.reputation - prev_reputation,
                    "progress": int(st.flags.get("progress", 0)) - prev_progress,
                },
                "detail_lines": [
                    f"你在遭遇战中不敌{sk.get('name')}，被迫后撤。",
                    *logs,
                    "你强行撤出战圈，暂且保住性命。",
                ],
                "encounter": {
                    "kind": "combat",
                    "name": sk.get("name"),
                    "style": sk.get("style"),
                    "faction": sk.get("faction"),
                    "origin": sk.get("origin"),
                },
                "intent_outcomes": {"combat_won": False, "negotiate_won": False, "target": sk.get("name")},
            }
            stage_notes = self._update_story_stage(Intent.COMBAT, sim_result)
            turn = self._generate_story_turn(
                action=f"在遭遇战中使出{skill}后败退",
                sim_result=sim_result,
                stage_notes=stage_notes,
            )
            turn["debug"]["skirmish"] = "lose_round"
            return turn

        sk["turn"] = int(sk.get("turn", 1)) + 1
        sk["last_log"] = logs
        return {
            "narration": "遭遇战仍在继续。\n" + "\n".join(logs),
            "options": self.state.last_options or [],
            "debug": {"skirmish": "ongoing", "skill": skill},
        }

    def start_boss_fight(self) -> tuple[bool, str]:
        if not self.is_boss_available():
            return False, "尚未到终章，无法挑战 Boss。"
        bs = self._boss_state()
        if bs.get("active"):
            return True, "Boss 战已经开始。"
        max_hp = 260 + self.state.martial_level * 18
        bs.update(
            {
                "active": True,
                "hp": max_hp,
                "max_hp": max_hp,
                "phase": 1,
                "turn": 1,
                "rage": 40,
                "next_move": "试探",
                "cooldowns": {"qg": 0, "zg": 0, "ng": 0, "jj": 0},
                "last_log": ["终章之门开启，天门宗师·夜无锋踏月而来。"],
                "won": False,
            }
        )
        return True, "终章 Boss 战已开启。"

    def boss_panel_text(self) -> str:
        if not self.is_boss_available():
            return "终章 Boss 面板：未解锁（推进主线至最后一章后可挑战）"
        if not bs.get("active"):
            return "终章 Boss 面板：已解锁，点击“开启 Boss 战”进入战斗。"
        logs = bs.get("last_log", [])[-6:]
        return (
            f"Boss: {bs.get('name')}\n"
            f"Boss HP: {bs.get('hp')}/{bs.get('max_hp')}  阶段: {bs.get('phase')}  回合: {bs.get('turn')}\n"
            f"你的状态: HP {self.state.health}/{self.state.max_health} | 体力 {self.state.stamina}/{self.state.max_stamina} | 内力 {self.state.inner_power}\n"
            f"怒气: {bs.get('rage', 0)}/100  Boss预兆: {bs.get('next_move', '未显')}\n"
            f"技能冷却: 轻功[{bs['cooldowns']['qg']}] 招架[{bs['cooldowns']['zg']}] 内功[{bs['cooldowns']['ng']}] 绝技[{bs['cooldowns']['jj']}]\n"
            "战斗日志:\n- " + "\n- ".join(logs)
        )

    def boss_skill_action(self, skill: str) -> TurnResult:
        bs = self._boss_state()
        if not self.is_boss_available():
            return {
                "narration": "你尚未走到终章，天门宗师仍隐于迷雾。",
                "options": self.state.last_options or [],
                "debug": {"boss": "not_unlocked"},
            }
        if not bs.get("active"):
            ok, msg = self.start_boss_fight()
            if not ok:
                return {"narration": msg, "options": self.state.last_options or [], "debug": {"boss": "start_failed"}}
            return {
                "narration": "终章战场铺开。请使用技能按钮出招：轻功 / 招架 / 内功 / 绝技。",
                "options": self.state.last_options or [],
                "debug": {"boss": "started"},
            }

        st = self.state
        cds: dict[str, int] = bs["cooldowns"]
        sk_map = {"轻功": "qg", "招架": "zg", "内功": "ng", "绝技": "jj"}
        sk = sk_map.get(skill, "")
        logs: list[str] = []

        # cooldown tick
        for k in cds:
            cds[k] = max(0, int(cds[k]) - 1)

        if sk == "" or cds.get(sk, 0) > 0:
            logs.append("你招式未成，只得仓促变招。")
            p_dmg = max(4, 7 + st.martial_level + self.rng.randint(0, 4))
            stamina_cost = 5
        elif sk == "qg":
            p_dmg = max(8, 12 + st.martial_level * 2 + self.rng.randint(0, 8))
            stamina_cost = 10
            cds["qg"] = 1
            logs.append("你施展轻功，踏影绕背，斜刺一剑。")
        elif sk == "zg":
            p_dmg = max(6, 9 + st.martial_level + self.rng.randint(0, 6))
            stamina_cost = 8
            cds["zg"] = 1
            st.flags["boss_guard_buff"] = 1
            logs.append("你沉肩收势，守中带攻，借力反震。")
        elif sk == "ng":
            p_dmg = max(12, 14 + st.inner_power // 10 + self.rng.randint(2, 10))
            stamina_cost = 14
            cds["ng"] = 2
            logs.append("你运转内功，真气贯剑，剑鸣如雷。")
        else:  # jj
            p_dmg = max(20, 20 + st.martial_level * 3 + self.rng.randint(4, 12))
            stamina_cost = 22
            if int(bs.get("rage", 0)) < 100:
                p_dmg = max(6, 10 + st.martial_level + self.rng.randint(0, 5))
                stamina_cost = 10
                logs.append("怒气未满，绝技只得化为强攻。")
            else:
                cds["jj"] = 3
                bs["rage"] = 0
                logs.append("你祭出绝技，一式破空，罡风裂石。")

        if st.stamina < stamina_cost:
            p_dmg = max(3, p_dmg // 2)
            logs.append("你体力不继，绝大部分劲力未能贯出。")
        st.stamina = max(0, st.stamina - stamina_cost)
        bs["hp"] = max(0, int(bs["hp"]) - p_dmg)
        bs["rage"] = min(100, int(bs.get("rage", 0)) + 10 + (4 if sk == "zg" else 0) + (3 if sk == "qg" else 0))
        logs.append(f"你对 Boss 造成 {p_dmg} 点伤害。")

        if bs["hp"] <= int(bs["max_hp"]) // 2 and bs["phase"] == 1:
            bs["phase"] = 2
            logs.append("Boss 气息陡变，第二阶段开启，招式更凶。")

        if bs["hp"] <= 0:
            bs["active"] = False
            bs["won"] = True
            st.flags["final_clear"] = True
            st.flags["stage_idx"] = len(MAIN_STORY)
            st.reputation += 30
            st.silver += 160
            ending = self._determine_ending()
            st.flags["ending"] = ending
            st.push_event("boss", "击败终章 Boss", {"name": bs.get("name")})
            bs["last_log"] = logs
            return {
                "narration": self._ending_narration(ending),
                "options": [],
                "debug": {"boss": "won", "ending": ending, "ending_reasons": self._ending_reason_map()},
            }

        # Boss counter-attack with telegraphed move
        move_pool = ["破军", "断岳", "回风", "追魂"]
        if int(bs.get("phase", 1)) >= 2:
            move_pool.extend(["天门坠", "裂夜"])
        move = self.rng.choice(move_pool)
        next_pred = self.rng.choice(move_pool)
        bs["next_move"] = next_pred
        move_bonus = {
            "破军": 6,
            "断岳": 10,
            "回风": 4,
            "追魂": 8,
            "天门坠": 12,
            "裂夜": 14,
        }.get(move, 6)
        base_enemy = 10 + bs["phase"] * 4 + move_bonus + self.rng.randint(0, 6)
        guard_bonus = 6 if st.flags.pop("boss_guard_buff", 0) else 0
        dmg = max(1, base_enemy - (st.martial_level + guard_bonus))
        st.health = max(0, st.health - dmg)
        logs.append(f"Boss 使出【{move}】，你受到 {dmg} 点伤害。")
        logs.append(f"你感到其下一式气机已起：{next_pred}。")
        if st.health == 0:
            st.health = max(12, st.max_health // 7)
            st.stamina = max(8, st.max_stamina // 8)
            bs["active"] = False
            bs["last_log"] = logs + ["你败退疗伤，Boss 战暂时中断。"]
            return {
                "narration": "你被重创后撤，暂退三十里。待调息后可再开终章决战。",
                "options": self.state.last_options or [],
                "debug": {"boss": "lose_round"},
            }

        bs["turn"] = int(bs["turn"]) + 1
        bs["last_log"] = logs
        return {
            "narration": "终章激斗仍在继续。\n" + "\n".join(logs),
            "options": self.state.last_options or [],
            "debug": {"boss": "ongoing", "skill": skill},
        }

    def _apply_intent_effect(self, intent: Intent, target: Optional[str]) -> dict[str, Any]:
        st = self.state
        delta = {"health": 0, "stamina": 0, "silver": 0, "reputation": 0, "progress": 0}
        detail_lines: list[str] = []
        intent_outcomes = {"combat_won": False, "negotiate_won": False, "target": target}

        encounter = random_encounter(self.rng, st.location)
        danger_tier = 1 + st.flags.get("stage_idx", 0) // 2

        if intent == Intent.TRAVEL:
            options = travel_options(st.location)
            if target in options:
                st.location = target or st.location
            else:
                st.location = self.rng.choice(options)
            delta["stamina"] -= self.rng.randint(4, 10)
            delta["progress"] += 1
            detail_lines.append(f"你赶往 {st.location}。")
        elif intent == Intent.REST:
            heal = self.rng.randint(10, 18)
            rec = self.rng.randint(14, 26)
            delta["health"] += heal
            delta["stamina"] += rec
            delta["progress"] += 1
            detail_lines.append(f"你调息疗伤，恢复气血 {heal}，体力 {rec}。")
        elif intent == Intent.QUERY:
            gain = self.rng.randint(1, 3)
            delta["reputation"] += gain
            delta["progress"] += 2
            detail_lines.append(f"你收集到关键江湖消息，声望 +{gain}。")
        elif intent == Intent.NEGOTIATE:
            win = self.rng.random() < 0.68
            if win:
                delta["silver"] += self.rng.randint(8, 26)
                delta["reputation"] += self.rng.randint(1, 3)
                delta["progress"] += 2
                intent_outcomes["negotiate_won"] = True
                detail_lines.append("交涉成功，对方愿意让步。")
            else:
                delta["reputation"] -= 1
                detail_lines.append("交涉受阻，局面僵持。")

            if target:
                current_rel = int(st.relations.get(target, 0))
                st.relations[target] = current_rel + (2 if win else -1)
        elif intent == Intent.COMBAT:
            current_stage = stage_by_index(int(st.flags.get("stage_idx", 0)))
            enemy = spawn_enemy(self.rng, danger_tier=danger_tier, stage_id=current_stage.id if current_stage else None)
            self._start_skirmish(enemy)
            detail_lines.extend(self._record_skirmish_facts(enemy_state=self._skirmish_state(), won=False))
            detail_lines.append(f"你与{enemy.name}正面撞上，对方来自{getattr(enemy, 'origin', '来路未明')}，隶属{getattr(enemy, 'faction', '江湖散人')}。")
            detail_lines.append("请使用侧栏技能按钮出招：轻功 / 招架 / 内功 / 绝技。")
            intent_outcomes["combat_started"] = True
        elif intent == Intent.EXPLORE:
            delta["stamina"] -= self.rng.randint(6, 12)
            delta["progress"] += 2
            detail_lines.append(f"你在{st.location}细细探查。")
            if encounter.kind in {"loot", "mystery"} and self.rng.random() < 0.65:
                loot = random_loot(self.rng)
                st.inventory.append(loot)
                detail_lines.append(f"你发现了：{loot}")
                if loot == "黑木令牌":
                    record_fact(st, "black_wood_token", True)
        elif intent == Intent.USE_ITEM:
            if target and target in st.inventory:
                if "止血" in target:
                    delta["health"] += self.rng.randint(14, 26)
                    detail_lines.append(f"你使用 {target}，伤势好转。")
                elif "回气" in target:
                    delta["stamina"] += self.rng.randint(16, 28)
                    detail_lines.append(f"你服下 {target}，真气回流。")
                else:
                    delta["reputation"] += 1
                    detail_lines.append(f"你谨慎使用 {target}，似乎有所裨益。")
                st.inventory.remove(target)
                delta["progress"] += 1
            else:
                detail_lines.append("你翻找包裹，却没找到合适之物。")
        elif intent == Intent.INVENTORY:
            detail_lines.append("你检视行囊，默记可用之物。")
        else:
            # Unknown input still advances a bit if it has action-like text.
            if len(target or "") > 0:
                delta["progress"] += 1
            detail_lines.append("你心中踟蹰，试探着迈出一步。")

        # Every turn advances half a day and may inject a lightweight time event.
        detail_lines.extend(self._advance_world_time())
        if encounter.kind == "combat" and intent not in {Intent.COMBAT, Intent.REST} and self.rng.random() < 0.3:
            chip = self.rng.randint(4, 10)
            delta["health"] -= chip
            detail_lines.append(f"暗处偷袭擦身而过，你仍受伤 {chip} 点。")

        return {
            "delta": delta,
            "detail_lines": detail_lines,
            "encounter": asdict(encounter),
            "intent_outcomes": intent_outcomes,
        }

    def _apply_delta(self, delta: dict[str, int]) -> None:
        st = self.state
        st.health += delta.get("health", 0)
        st.stamina += delta.get("stamina", 0)
        st.silver += delta.get("silver", 0)
        st.reputation += delta.get("reputation", 0)
        st.flags["progress"] = st.flags.get("progress", 0) + delta.get("progress", 0)

        # growth curve for 2-3h play
        progress = st.flags["progress"]
        st.martial_level = 1 + progress // 14
        st.inner_power = min(180, progress * 2 + st.reputation)

        if st.silver < 0:
            st.silver = 0

    def _update_story_stage(self, intent: Intent, sim_result: dict[str, Any]) -> list[str]:
        st = self.state
        notes: list[str] = []
        idx = int(st.flags.get("stage_idx", 0))
        current = stage_by_index(idx)
        if not current:
            return notes

        counters = self._ensure_objective_counters()
        if intent == Intent.QUERY:
            counters["query_count"] += 1
        if intent == Intent.EXPLORE:
            counters["explore_count"] += 1
        outcomes = sim_result.get("intent_outcomes") if isinstance(sim_result.get("intent_outcomes"), dict) else {}
        if bool(outcomes.get("combat_won")):
            counters["combat_win"] += 1
        if bool(outcomes.get("negotiate_won")):
            counters["negotiate_win"] += 1
        st.flags["objective_counters"] = counters

        progress_ready = st.flags.get("progress", 0) >= current.required_progress
        goal_ready = self._is_stage_goal_met(idx, counters, st)
        if progress_ready and goal_ready:
            st.flags["stage_idx"] = idx + 1
            st.flags["stage_enter_turn"] = int(st.flags.get("turn", 0))
            st.flags["pending_stage_intro_idx"] = idx + 1
            st.flags[current.unlock_flag or f"stage_{idx+1}_done"] = True
            st.reputation += current.reward_reputation
            st.silver += current.reward_silver
            st.push_event("main_story", f"完成主线章节：{current.title}", {"stage": current.id})
            notes.append(f"【主线推进】{current.title} 完成，声望+{current.reward_reputation}，银两+{current.reward_silver}")
            st.flags["objective_counters"] = {
                "query_count": 0,
                "combat_win": 0,
                "negotiate_win": 0,
                "explore_count": 0,
            }
        elif progress_ready and not goal_ready:
            notes.append("【主线未满足】进度已达标，但关键行动尚不足。")

        # side quest trigger
        active = set(st.flags.get("active_side_quests", []))
        done = set(st.flags.get("done_side_quests", []))
        for q in SIDE_QUESTS:
            qid = str(q["id"])
            if qid in active or qid in done:
                continue
            trigger_locs = q.get("trigger_locations") if isinstance(q.get("trigger_locations"), list) else []
            trigger_intents = q.get("trigger_intents") if isinstance(q.get("trigger_intents"), list) else []
            trigger_by_action = intent.value in {str(x) for x in trigger_intents}
            if st.location in trigger_locs and trigger_by_action and self.rng.random() < 0.65:
                active.add(qid)
                notes.append(f"【支线触发】{q['title']}: {q['objective']}")

        # side quest settle chance
        still_active: set[str] = set(active)
        for q in SIDE_QUESTS:
            qid = str(q["id"])
            if qid not in still_active:
                continue
            resolve_intents = q.get("resolve_intents") if isinstance(q.get("resolve_intents"), list) else []
            should_settle = intent.value in {str(x) for x in resolve_intents}
            if not should_settle and self.rng.random() < 0.08:
                should_settle = True

            if should_settle:
                reward = q["reward"]
                st.silver += int(reward.get("silver", 0))
                st.reputation += int(reward.get("reputation", 0))
                item = reward.get("item")
                if item:
                    st.inventory.append(str(item))
                still_active.remove(qid)
                done.add(qid)
                notes.append(f"【支线完成】{q['title']}，获得奖励。")

        st.flags["active_side_quests"] = sorted(still_active)
        st.flags["done_side_quests"] = sorted(done)
        return notes

    def _build_prompt_payload(self, user_action: str, sim_result: dict[str, Any]) -> str:
        st = self.state
        idx = int(st.flags.get("stage_idx", 0))
        current_stage = MAIN_STORY[idx] if idx < len(MAIN_STORY) else None
        cleaned_action = (user_action or "").replace("【主线建议】", "").strip()
        if not self._memory_doc:
            self._sync_memory_document()

        raw_notes = sim_result.get("notes") if isinstance(sim_result.get("notes"), list) else []
        cleaned_notes: list[str] = []
        for n in raw_notes:
            txt = self._clean_story_note(n)
            if "主线建议" in txt:
                continue
            if txt:
                cleaned_notes.append(txt)

        sim_payload = dict(sim_result)
        sim_payload["notes"] = cleaned_notes[:4]

        state_public = st.to_public_dict()
        fact_events_raw = state_public.get("fact_events_recent")
        fact_events_recent = fact_events_raw if isinstance(fact_events_raw, list) else []
        npc_registry_raw = state_public.get("npc_registry")
        npc_registry = npc_registry_raw if isinstance(npc_registry_raw, dict) else {}
        memory_view = prompt_memory_view(self._memory_doc, current_stage_idx=idx)
        story_so_far = memory_view.get("story_so_far") if isinstance(memory_view.get("story_so_far"), list) else []
        current_arc_memory = memory_view.get("current_arc") if isinstance(memory_view.get("current_arc"), list) else []
        chapter_memory = memory_view.get("chapter_memory") if isinstance(memory_view.get("chapter_memory"), dict) else {}

        npcs_known: list[dict[str, Any]] = []
        for name, data in npc_registry.items():
            if not isinstance(name, str) or not isinstance(data, dict):
                continue
            npcs_known.append(
                {
                    "name": name,
                    "relation": int(data.get("relation", 0)),
                    "last_loc": str(data.get("last_loc", "")),
                    "note": str(data.get("note", "")),
                    "interactions": list(data.get("interactions", []))[-3:] if isinstance(data.get("interactions"), list) else [],
                }
            )
        npcs_known = npcs_known[:8]

        chapter_progress_narrative = self._chapter_progress_narrative(idx)
        recent_fact_timeline = self._recent_fact_timeline()

        payload = {
            "player_action": cleaned_action,
            "state": state_public,
            "world_location_desc": LOCATIONS.get(st.location, {}).get("desc", ""),
            "sim_result": sim_payload,
            "story_outline_summary": self._story_outline_summary(),
            "final_goal_summary": FINAL_GOAL_SUMMARY,
            "allowed_intents": [
                Intent.EXPLORE.value,
                Intent.COMBAT.value,
                Intent.QUERY.value,
                Intent.NEGOTIATE.value,
                Intent.TRAVEL.value,
                Intent.REST.value,
                Intent.USE_ITEM.value,
            ],
            "story_stage": {
                "index": idx,
                "title": current_stage.title if current_stage else "终局已开",
                "objective": current_stage.objective if current_stage else "完成江湖终局",
                "location_hint": current_stage.location_hint if current_stage else "自由探索",
            },
            "current_chapter_arc": {
                "intro": current_stage.chapter_intro if current_stage else "终局之后，余波未散。",
                "conflict": current_stage.chapter_conflict if current_stage else "终局已决，等待回响。",
                "significance": current_stage.chapter_significance if current_stage else "你已走到故事尽头。",
            },
            "stage_guidance": {
                "win_guidance": current_stage.win_guidance if current_stage else "",
                "preferred_intents": list(current_stage.preferred_intents) if current_stage else [],
            },
            "chapter_hook": self._chapter_hook(idx),
            "story_so_far": story_so_far,
            "story_memory_current_arc": current_arc_memory,
            "chapter_memory": chapter_memory,
            "npcs_known": npcs_known,
            "known_facts": dict(st.known_facts),
            "recent_fact_timeline": recent_fact_timeline,
            "fact_events_recent": fact_events_recent,
            "chapter_progress_narrative": chapter_progress_narrative,
            "time_context": {
                "day": st.day,
                "phase": self._time_phase(),
                "label": self._time_label(),
                "memory_timestamp": self._memory_timestamp(),
            },
            "memory_doc": {
                "doc_id": self.memory_doc_id,
                "path": self.memory_doc_path(),
                "updated_at": str(self._memory_doc.get("updated_at", "")),
            },
            "narrative_tone": self._narrative_tone(st),
            "chapter_timing": self._get_stage_timing(),
            "instruction": "请续写连贯剧情，必须在主线大纲下按时间顺序承接 memory_timestamp/memory_index 所示的既有故事，并给出分化路线的选项。",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _apply_stage_guidance_to_options(self, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        idx = int(self.state.flags.get("stage_idx", 0))
        stage = stage_by_index(idx)
        if not stage or not stage.preferred_intents:
            return options

        preferred = set(stage.preferred_intents)

        def rank(opt: dict[str, Any]) -> tuple[int, int]:
            intent = str(opt.get("intent", ""))
            risk = str(opt.get("risk", "medium"))
            risk_rank = {"low": 0, "medium": 1, "high": 2}.get(risk, 1)
            return (0 if intent in preferred else 1, risk_rank)

        ordered = sorted(options, key=rank)
        for opt in ordered:
            if str(opt.get("intent", "")) in preferred:
                opt["hint"] = "mainline"
        return ordered

    @staticmethod
    def _dedup_and_balance_options(options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        dedup: list[dict[str, Any]] = []
        seen_text: set[str] = set()
        seen_intent: set[str] = set()
        for opt in options:
            text = str(opt.get("text", "")).strip()
            intent = str(opt.get("intent", "")).strip()
            if not text or text in seen_text:
                continue
            if intent and intent in seen_intent and len(dedup) >= 2:
                continue
            seen_text.add(text)
            if intent:
                seen_intent.add(intent)
            dedup.append(opt)
            if len(dedup) >= 4:
                break
        return dedup

    def _fallback_turn(self, sim_lines: list[str]) -> TurnResult:
        st = self.state
        options = [
            {"id": "o1", "text": "继续探索周边", "intent": "explore", "target": None, "risk": "medium"},
            {"id": "o2", "text": "就地调息休整", "intent": "rest", "target": None, "risk": "low"},
            {"id": "o3", "text": "前往下一处地界", "intent": "travel", "target": self.rng.choice(travel_options(st.location)), "risk": "medium"},
        ]
        narration = "\n".join(sim_lines[:8]) + f"\n你此刻身在{st.location}，江湖暗流仍在涌动。"
        return {"narration": narration, "options": options, "debug": {"fallback": True}}

    def _generate_story_turn(self, *, action: str, sim_result: dict[str, Any], stage_notes: list[str]) -> TurnResult:
        st = self.state
        detail_lines = sim_result.get("detail_lines") if isinstance(sim_result.get("detail_lines"), list) else []
        sim_lines = [*detail_lines, *stage_notes]
        system_messages: list[str] = []

        payload = self._build_prompt_payload(action, sim_result | {"notes": stage_notes})
        response = self.client.chat(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ]
        )
        llm_meta = getattr(self.client, "last_meta", {})
        llm_mode = str(llm_meta.get("mode", "unknown"))
        st.flags["last_llm_mode"] = llm_mode
        st.flags["last_llm_error"] = str(llm_meta.get("error", ""))

        parsed, parse_debug = parse_llm_turn(response)
        if not parsed:
            turn = self._fallback_turn(sim_lines)
            turn["debug"]["llm_parse"] = parse_debug
            st.flags["llm_parse_fail_count"] = int(st.flags.get("llm_parse_fail_count", 0)) + 1
        else:
            if llm_mode == "online" and self._narration_too_similar(parsed.narration):
                retry_response = self.client.chat(
                    [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "system",
                            "content": "上一版 narration 与最近几段过于相似。请避免重复近三回合的句式、冲突描述和收束语，必须明确写出新的推进点与新的因果。",
                        },
                        {"role": "user", "content": payload},
                    ]
                )
                retry_parsed, retry_debug = parse_llm_turn(retry_response)
                if retry_parsed:
                    parsed = retry_parsed
                    parse_debug["retry_due_to_similarity"] = True
                    parse_debug["retry_parse"] = retry_debug
            turn = {
                "narration": parsed.narration,
                "options": [o.model_dump() for o in parsed.options],
                "debug": {"llm_parse": parse_debug},
            }
            st.flags["llm_parse_fail_count"] = 0

        memory_summary = self._fallback_memory_summary(action, sim_result, stage_notes)
        if parsed and str(parsed.memory_summary or "").strip():
            memory_summary = str(parsed.memory_summary).strip()

        turn["debug"]["llm_mode"] = llm_mode
        if llm_mode != "online":
            turn["debug"]["llm_fallback_reason"] = str(llm_meta.get("error", "fallback"))
            reason = str(llm_meta.get("error", "fallback") or "fallback")
            system_messages.append(f"【叙事状态】在线叙事模型当前不可用，已切换为离线兜底生成。原因：{reason}。")

        turn["options"] = self._dedup_and_balance_options(turn.get("options", []))
        turn["options"] = self._apply_stage_guidance_to_options(turn.get("options", []))

        if not any(o.get("intent") == "travel" for o in turn["options"]):
            travel_target = self.rng.choice(travel_options(st.location))
            turn["options"].append(
                {
                    "id": "ox",
                    "text": f"转往{travel_target}",
                    "intent": "travel",
                    "target": travel_target,
                    "risk": "medium",
                }
            )
            turn["options"] = turn["options"][:4]

        self._record_story_memory(
            action=action,
            narration=str(turn.get("narration") or ""),
            sim_result=sim_result,
            stage_notes=stage_notes,
            memory_summary=memory_summary,
        )
        chapter_messages = self._consume_pending_chapter_intro()
        if chapter_messages:
            system_messages.extend(chapter_messages)
        if system_messages:
            turn["system_messages"] = system_messages
        st.last_options = turn["options"]
        return turn

    def step(self, user_text: str) -> TurnResult:
        st = self.state
        if bool(st.flags.get("game_over")):
            return self._build_game_over_turn(str(st.flags.get("game_over_reason") or "章节失败"))

        if self.is_boss_active():
            return {
                "narration": "你正处于终章 Boss 战。请使用右侧技能按钮：轻功 / 招架 / 内功 / 绝技。",
                "options": self.state.last_options or [],
                "debug": {"boss": "need_skill_button"},
            }
        if self.is_skirmish_active():
            return {
                "narration": "你正处于遭遇战中。请使用右侧技能按钮：轻功 / 招架 / 内功 / 绝技。",
                "options": self.state.last_options or [],
                "debug": {"skirmish": "need_skill_button"},
            }
        st.flags["turn"] = st.flags.get("turn", 0) + 1

        timeout_turn = self._check_stage_timeout()
        if timeout_turn:
            return timeout_turn

        normalized = self._normalize_input(user_text)
        selected_option = self._match_last_option(user_text)
        if selected_option:
            raw_intent = str(selected_option.get("intent") or "").strip()
            try:
                intent = Intent(raw_intent)
            except Exception:
                intent = classify_intent_detailed(normalized).intent
            target = selected_option.get("target") if selected_option.get("target") is not None else None
            intent_guess = classify_intent_detailed(normalized)
            target_guess = extract_target_detailed(normalized)
        else:
            intent_guess = classify_intent_detailed(normalized)
            target_guess = extract_target_detailed(normalized)
            intent = intent_guess.intent
            target = target_guess.target

        if intent in {Intent.TRAVEL, Intent.USE_ITEM, Intent.NEGOTIATE} and target is None and intent_guess.confidence >= 0.45:
            clarification = {
                "narration": "你给出了行动方向，但对象不够明确。请补充要前往的地点、要拜访的人，或要使用的物品。",
                "options": self._build_clarification_options(intent),
                "debug": {"clarify": True, "intent_conf": intent_guess.confidence, "target_conf": target_guess.confidence},
            }
            st.last_options = clarification["options"]
            return clarification

        sim_result = self._apply_intent_effect(intent, target)
        self._apply_delta(sim_result["delta"])

        stage_notes = self._update_story_stage(intent, sim_result)
        sim_lines = [*sim_result["detail_lines"], *stage_notes]
        st.push_event(
            "turn",
            f"行动：{normalized[:20]}",
            {"intent": intent.value, "target": target, "delta": sim_result["delta"], "notes": sim_lines[:5]},
        )
        st.compact_history(self.settings.max_history_events)

        fix = enforce_state_invariants(st)
        if fix.changed:
            st.push_event("consistency_fix", "状态已自动修复", {"notes": fix.notes})

        if bool(sim_result.get("intent_outcomes", {}).get("combat_started")):
            turn = {
                "narration": "你猛然撞入一场短兵相接的遭遇战。对手已经逼近，请使用右侧技能按钮出招：轻功 / 招架 / 内功 / 绝技。",
                "options": self.state.last_options or [],
                "debug": {"skirmish": "started"},
            }
            self._record_story_memory(
                action=normalized,
                narration=str(turn.get("narration") or ""),
                sim_result=sim_result,
                stage_notes=stage_notes,
                memory_summary=self._fallback_memory_summary(normalized, sim_result, stage_notes),
            )
            return turn
        return self._generate_story_turn(action=normalized, sim_result=sim_result, stage_notes=stage_notes)

    def _determine_ending(self) -> str:
        st = self.state
        if st.martial_level >= 7 and st.inner_power >= 120:
            return "武道极境"

        npc_allies = 0
        registry = self._ensure_npc_registry()
        for data in registry.values():
            if isinstance(data, dict) and int(data.get("relation", 0)) > 5:
                npc_allies += 1
        if st.reputation >= 55 and npc_allies >= 3:
            return "义满江湖"

        if st.silver >= 200 and st.sect is not None:
            return "财富权谋"

        if bool(st.known_facts.get("black_wood_token")) and int(st.flags.get("stage_idx", 0)) >= 6:
            return "解谜真相"

        return "孤侠天涯"

    def _ending_reason_map(self) -> dict[str, bool]:
        st = self.state
        npc_allies = 0
        registry = self._ensure_npc_registry()
        for data in registry.values():
            if isinstance(data, dict) and int(data.get("relation", 0)) > 5:
                npc_allies += 1
        return {
            "wudao": st.martial_level >= 7 and st.inner_power >= 120,
            "yiman": st.reputation >= 55 and npc_allies >= 3,
            "caifu": st.silver >= 200 and st.sect is not None,
            "zhenxiang": bool(st.known_facts.get("black_wood_token")) and int(st.flags.get("stage_idx", 0)) >= 6,
            "npc_allies_ge3": npc_allies >= 3,
        }

    @staticmethod
    def _ending_narration(ending: str) -> str:
        endings = {
            "武道极境": "你立于天门残阶，剑锋垂落而气机不散。夜风掠过时，山川像被你的呼吸牵动。昔日难关皆成磨刀石，诸派高手不再只以名号称你，而以一式一势衡量你的境界。你没有立即开宗立派，只在江湖中留下几场无人能忘的论剑。后来人提起此夜，常说宗师并非一战封名，而是在无数取舍后仍能守住本心。",
            "义满江湖": "夜无锋败退后，最先赶来的不是争名逐利之徒，而是你曾经救过、帮过、信过的人。灯火沿山道排开，旧友递来酒囊，陌路拱手致谢。你明白江湖最重的不是兵刃锋芒，而是关键时刻有人愿与你并肩。自此，各地纷争多请你裁断，你不争盟主之位，却在众望中成了真正的侠义旗帜。",
            "财富权谋": "终章落幕后，你没有沉湎于掌声，而是顺势整合商路、镖路与情报网。银两汇成潮水，门派与市井都不得不重新计算你的分量。你以财富换秩序，以秩序换筹码，最终把散乱江湖织成可控棋盘。人们或敬或惧，却都承认一个事实：你让刀光剑影之外，也有了新的规则。",
            "解谜真相": "天门石壁后的旧痕与黑木令牌相合，尘封多年的暗线终于贯通。你循着残卷与口供拼出完整真相，揭开了当年血案背后被刻意掩埋的人与局。夜无锋之败只是表层，真正被你斩断的是延续多年的谎言。江湖因此动荡，也因此清明。你没有把答案据为己有，而是将证据公诸于世，让后来者不再在黑暗中摸索。",
            "孤侠天涯": "大战过后，山门寂静，群峰只余风声。你收剑入鞘，没有停在任何人的赞辞里。有人说你错过了立名立业的最好时机，也有人说你本就不该被任何名目束缚。你沿着旧路继续远行，偶尔在酒馆角落听见自己的传闻，真假参半，却都与当下无关。江湖辽阔，你仍是那个向未知走去的人。",
        }
        return endings.get(ending, endings["孤侠天涯"])

    def export_story(self) -> str:
        st = self.state
        story_memory = self._ensure_story_memory()
        narrations = self._ensure_story_archive()
        stage_titles = [s.title for s in MAIN_STORY]
        current_stage = int(st.flags.get("stage_idx", 0))
        chapter_line = "、".join(stage_titles[: max(1, min(current_stage + 1, len(stage_titles)))])

        lines: list[str] = []
        lines.append("《江湖织梦·个人传》")
        lines.append(f"主角：{st.name}")
        lines.append(f"章节轨迹：{chapter_line}")
        lines.append("")
        lines.append("【回目摘要】")
        for it in story_memory:
            if not isinstance(it, dict):
                continue
            turn = int(it.get("turn", 0))
            summary = str(it.get("summary", "")).strip()
            if summary:
                memory_timestamp = str(it.get("memory_timestamp") or it.get("time_label") or "").strip()
                prefix = f"{memory_timestamp} 第{turn}回" if memory_timestamp else f"第{turn}回"
                lines.append(f"{prefix}：{summary}")
        lines.append("")
        lines.append("【叙事原文】")
        for idx, nar in enumerate(narrations, start=1):
            text = str(nar).strip()
            if not text:
                continue
            lines.append(f"第{idx}段")
            lines.append(text)
            lines.append("")

        if bool(st.flags.get("final_clear")):
            ending = str(st.flags.get("ending", "孤侠天涯"))
            lines.append(f"【终局】{ending}")
            lines.append(self._ending_narration(ending))

        return "\n".join(lines).strip()

    def state_panel_text(self) -> str:
        st = self.state
        idx = int(st.flags.get("stage_idx", 0))
        stage = stage_by_index(idx)
        return (
            f"地点: {st.location}\n"
            f"天数: {st.day}  回合: {st.flags.get('turn', 0)}\n"
            f"气血: {st.health}/{st.max_health}  体力: {st.stamina}/{st.max_stamina}\n"
            f"声望: {st.reputation}  银两: {st.silver}\n"
            f"武学等级: {st.martial_level}  内力: {st.inner_power}\n"
            f"背包: {', '.join(st.inventory[-8:]) if st.inventory else '无'}\n"
            f"当前主线: {(stage.title + ' - ' + stage.objective) if stage else '终局已完成'}\n"
            f"活跃支线: {', '.join(st.flags.get('active_side_quests', [])) or '无'}\n"
        )

