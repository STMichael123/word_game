from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Optional

from openai import OpenAI


@dataclass(frozen=True)
class ChatParams:
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.9
    top_p: float = 0.9
    max_tokens: int = 700


class LLMClient:
    def __init__(self, params: ChatParams):
        self._params = params
        self._client = OpenAI(base_url=params.base_url, api_key=params.api_key, timeout=25.0)
        self.last_meta: dict[str, str] = {"mode": "online", "status": "init"}

    def chat(self, messages: list[dict[str, str]]) -> str:
        try:
            resp = _create_chat_completion(
                self._client,
                model=self._params.model,
                messages=messages,
                temperature=self._params.temperature,
                top_p=self._params.top_p,
                max_tokens=self._params.max_tokens,
            )
            self.last_meta = {"mode": "online", "status": "ok"}
            return (resp.choices[0].message.content or "").strip()
        except Exception as e:
            # Fail soft so UI never hangs when remote API/network is unstable.
            self.last_meta = {
                "mode": "offline-fallback",
                "status": "error",
                "error": e.__class__.__name__,
            }
            offline = OfflineLLMClient()
            txt = offline.chat(messages)
            self.last_meta["fallback"] = "offline_client"
            return txt


def probe_connection(*, base_url: str, api_key: Optional[str], model: str) -> dict[str, str | bool]:
    if not api_key:
        return {
            "ok": False,
            "mode": "offline",
            "reason": "missing_api_key",
            "message": "未配置在线模型密钥。",
        }

    try:
        client = OpenAI(base_url=base_url, api_key=api_key, timeout=20.0)
        resp = _create_chat_completion(
            client,
            model=model,
            messages=[{"role": "user", "content": "Reply with a tiny json object containing ok."}],
            temperature=0,
            top_p=1,
            max_tokens=4,
        )
        content = (resp.choices[0].message.content or "").strip()
        return {
            "ok": True,
            "mode": "online",
            "reason": "ok",
            "message": content or "ok",
        }
    except Exception as e:
        return {
            "ok": False,
            "mode": "offline-fallback",
            "reason": e.__class__.__name__,
            "message": str(e),
        }


def _create_chat_completion(
    client: OpenAI,
    *,
    model: str,
    messages: list[dict[str, str]],
    temperature: float,
    top_p: float,
    max_tokens: int,
):
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "top_p": top_p,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    try:
        return client.chat.completions.create(**kwargs)
    except Exception as e:
        message = str(e)
        if "max_tokens" in message and "max_completion_tokens" in message:
            kwargs.pop("max_tokens", None)
            kwargs["max_completion_tokens"] = max_tokens
            try:
                return client.chat.completions.create(**kwargs)
            except Exception as retry_error:
                message = str(retry_error)
                if "response_format" in message and "unsupported" in message.lower():
                    kwargs.pop("response_format", None)
                    return client.chat.completions.create(**kwargs)
                raise
        if "response_format" in message and "unsupported" in message.lower():
            kwargs.pop("response_format", None)
            return client.chat.completions.create(**kwargs)
        raise


class OfflineLLMClient(LLMClient):
    def __init__(self):
        self.last_meta: dict[str, str] = {"mode": "offline", "status": "ok"}

    @staticmethod
    def _as_int(value: object, default: int) -> int:
        try:
            return int(value)
        except Exception:
            return default

    def _extract_payload(self, messages: list[dict[str, str]]) -> dict:
        user_text = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
        if not user_text:
            return {}
        try:
            obj = json.loads(user_text)
            if isinstance(obj, dict):
                return obj
        except Exception:
            return {}
        return {}

    @staticmethod
    def _clean_action(text: str) -> str:
        t = (text or "").strip()
        t = t.replace("【主线建议】", "")
        t = re.sub(r"\s+", " ", t)
        return t.strip(" \t\r\n\"'“”") or "谨慎前行"

    @staticmethod
    def _pick(items: list[str], seed: int, step: int = 0) -> str:
        if not items:
            return ""
        idx = (seed + step * 7) % len(items)
        return items[idx]

    @staticmethod
    def _safe_note(note: str) -> str:
        txt = (note or "").strip()
        if txt.startswith("【") and "】" in txt:
            txt = txt.split("】", 1)[1].strip()
        return txt.rstrip("。！？!?")

    @staticmethod
    def _unique_options(candidates: list[dict]) -> list[dict]:
        seen_text: set[str] = set()
        seen_intent: set[str] = set()
        out: list[dict] = []
        for c in candidates:
            text = str(c.get("text") or "").strip()
            intent = str(c.get("intent") or "").strip()
            if not text or not intent:
                continue
            if text in seen_text:
                continue
            # Keep option intents broad, avoid 4 nearly identical actions.
            if intent in seen_intent and intent not in {"combat", "explore"}:
                continue
            seen_text.add(text)
            seen_intent.add(intent)
            out.append(c)
            if len(out) >= 4:
                break
        return out

    @staticmethod
    def _inventory_usable_items(inventory: list[object]) -> list[str]:
        out: list[str] = []
        for item in inventory:
            text = str(item or "").strip()
            if any(k in text for k in ("止血", "回气", "丹", "散", "药", "酒", "膏")):
                out.append(text)
        return out[:3]

    def _build_narration(self, payload: dict) -> str:
        action = self._clean_action(str(payload.get("player_action") or "谨慎前行"))
        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
        location = str(state.get("location") or "江湖")
        day = self._as_int(state.get("day"), 1)
        stamina = self._as_int(stats.get("stamina"), 100)
        health = self._as_int(stats.get("health"), 100)
        time_context = payload.get("time_context") if isinstance(payload.get("time_context"), dict) else {}
        time_label = str(time_context.get("memory_timestamp") or time_context.get("label") or f"第{day}日").strip()

        stage = payload.get("story_stage") if isinstance(payload.get("story_stage"), dict) else {}
        stage_idx = self._as_int(stage.get("index"), 0)
        stage_title = str(stage.get("title") or "江湖行路")
        objective = str(stage.get("objective") or "顺势而为")
        chapter_arc = payload.get("current_chapter_arc") if isinstance(payload.get("current_chapter_arc"), dict) else {}
        chapter_intro = self._safe_note(str(chapter_arc.get("intro") or ""))
        chapter_conflict = self._safe_note(str(chapter_arc.get("conflict") or ""))
        chapter_significance = self._safe_note(str(chapter_arc.get("significance") or ""))
        story_so_far = payload.get("story_so_far") if isinstance(payload.get("story_so_far"), list) else []
        current_arc_memory = payload.get("story_memory_current_arc") if isinstance(payload.get("story_memory_current_arc"), list) else []
        recent_fact_timeline = payload.get("recent_fact_timeline") if isinstance(payload.get("recent_fact_timeline"), list) else []
        chapter_progress_narrative = str(payload.get("chapter_progress_narrative") or "").strip()
        known_facts = payload.get("known_facts") if isinstance(payload.get("known_facts"), dict) else {}

        sim_result = payload.get("sim_result") if isinstance(payload.get("sim_result"), dict) else {}
        delta = sim_result.get("delta") if isinstance(sim_result.get("delta"), dict) else {}
        detail_lines_raw = sim_result.get("detail_lines") if isinstance(sim_result.get("detail_lines"), list) else []
        detail_lines = [self._safe_note(str(x)) for x in detail_lines_raw if self._safe_note(str(x))]
        stage_notes_raw = sim_result.get("notes") if isinstance(sim_result.get("notes"), list) else []
        stage_notes = [self._safe_note(str(x)) for x in stage_notes_raw if self._safe_note(str(x))]

        memory_hint = ""
        memory_hint_time = ""
        for item in reversed(story_so_far[-3:]):
            if not isinstance(item, dict):
                continue
            summary = self._safe_note(
                str(item.get("memory_index") or item.get("story_significance") or item.get("summary") or item.get("action") or "")
            )
            if summary:
                memory_hint = summary
                memory_hint_time = self._safe_note(str(item.get("memory_timestamp") or item.get("time_label") or ""))
                break

        if not memory_hint:
            for item in reversed(current_arc_memory[-3:]):
                if not isinstance(item, dict):
                    continue
                summary = self._safe_note(
                    str(item.get("memory_index") or item.get("chapter_goal_effect") or item.get("summary") or "")
                )
                if summary:
                    memory_hint = summary
                    memory_hint_time = self._safe_note(str(item.get("memory_timestamp") or item.get("time_label") or ""))
                    break

        fact_hint = ""
        if known_facts.get("final_master_lair_map"):
            fact_hint = "宗师秘图已经在手，说明你离夜无锋真正藏身之处只差最后几步。"
        elif known_facts.get("black_pine_is_front"):
            fact_hint = "你已经确认黑松会只是外壳，眼前所有冲突都开始指向更深的宗师布局。"
        elif known_facts.get("tianmen_master_nearby"):
            fact_hint = "那句宗师将临天门的临死喊声仍在耳边，提醒你终局随时可能提前压下来。"
        elif known_facts.get("leader_heading_to_alliance"):
            fact_hint = "首领将赴会盟的消息让你明白，局势很快就会从暗潮转入公开拆局。"
        elif known_facts.get("black_wood_token"):
            fact_hint = "黑木令牌在袖中发沉，提醒你自己已经摸到黑松会真正的指挥层。"
        elif known_facts.get("escort_token"):
            fact_hint = "你手里的镖局信物说明此局早已牵扯到更深的旧账与内鬼。"
        elif known_facts.get("black_pine_activity"):
            fact_hint = "黑松会的影子始终在暗处牵引局势。"

        intro_clause = chapter_intro or f"{location}的风声里仍裹着未散的杀机"
        lines: list[str] = [f"{time_label}，{location}一带天色低沉。{intro_clause}，而你选择了“{action}”。"]

        if memory_hint:
            memory_prefix = f"{memory_hint_time}的余波" if memory_hint_time else "上一回合的余波"
            lines.append(f"你心里还压着{memory_prefix}：{memory_hint}，因此这一举并不是临时起意，而是顺着既有线索继续逼近局心。")

        if detail_lines:
            lines.append("这一番周旋之下，" + "；".join(detail_lines[:3]) + "。")
        elif stage_notes:
            lines.append("局势并未停滞，" + "；".join(stage_notes[:2]) + "。")

        encounter = sim_result.get("encounter") if isinstance(sim_result.get("encounter"), dict) else {}
        kind = str(encounter.get("kind") or "")
        if kind == "combat" and not detail_lines:
            lines.append("刀兵气扑面而来，说明对手已经不打算再躲在幕后试探。")
        elif kind == "npc" and not detail_lines:
            lines.append("对方话里藏锋，显然有人正在借市井人情替更大的势力探路。")

        fail_markers = ("没找到", "受阻", "踟蹰", "失败", "未能", "落空")
        is_failed_turn = any(any(m in x for m in fail_markers) for x in detail_lines)
        if self._as_int(delta.get("progress"), 0) <= 0 and detail_lines:
            is_failed_turn = True

        if is_failed_turn:
            lines.append("只是这一招还没真正撬开章法，眼前的阻滞说明你还欠一枚更硬的筹码，或者还缺一个愿意开口的人。")
        elif health <= 35:
            lines.append("可你身上旧伤未平，若再强行硬闯，下一次碰撞很可能就不是试探，而是生死。")
        elif stamina <= 25:
            lines.append("你能感觉到气息已乱，若不稍作调匀，后面的每一步都会比表面看上去更凶险。")
        else:
            pressure = chapter_conflict.replace("本章冲突", "").lstrip("：:，,在于") if chapter_conflict else f"这一章真正的难处，在于{objective}"
            lines.append(f"而你也越发看清，这一章的关键并不只是{objective}，更在于{pressure}。")

        if fact_hint:
            lines.append(fact_hint)
        elif recent_fact_timeline:
            lines.append("你迅速把近几回合最关键的线索重新串了起来：" + self._safe_note(str(recent_fact_timeline[-1])) + "。")
        elif chapter_significance:
            lines.append(f"你明白这一步之所以重要，是因为{chapter_significance}。")
        else:
            lines.append(f"{stage_title}这一章的水面看似平静，底下其实已经开始换流。")

        if chapter_progress_narrative:
            lines.append(self._safe_note(chapter_progress_narrative) + "。")

        narration = "".join(lines)
        if len(narration) < 170:
            narration += "你没有立刻停下，而是把听到的话、见到的人与旧线索反复对照，隐约察觉眼前这点波澜只是更大风暴掀开的前沿。"
        return narration[:320]

    def _build_options(self, payload: dict) -> list[dict]:
        state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
        stats = state.get("stats") if isinstance(state.get("stats"), dict) else {}
        stage = payload.get("story_stage") if isinstance(payload.get("story_stage"), dict) else {}
        guidance = payload.get("stage_guidance") if isinstance(payload.get("stage_guidance"), dict) else {}
        location = str(state.get("location") or "此地")
        day = self._as_int(state.get("day"), 1)
        stamina = self._as_int(stats.get("stamina"), 100)
        health = self._as_int(stats.get("health"), 100)
        stage_idx = self._as_int(stage.get("index"), 0)
        objective = str(stage.get("objective") or "推进主线")
        side_quests = state.get("active_side_quests") if isinstance(state.get("active_side_quests"), list) else []
        inventory = state.get("inventory") if isinstance(state.get("inventory"), list) else []
        preferred_intents = [str(x) for x in guidance.get("preferred_intents", [])] if isinstance(guidance.get("preferred_intents"), list) else []
        seed = day * 11 + stage_idx * 23 + len(location)

        candidates: list[dict] = []

        if "query" in preferred_intents:
            candidates.append({"text": f"继续打听与“{objective}”有关的消息", "intent": "query", "target": None, "risk": "low"})
        elif "combat" in preferred_intents:
            candidates.append({"text": "主动逼近危险地带，争取正面破局", "intent": "combat", "target": None, "risk": "high"})
        elif "negotiate" in preferred_intents:
            candidates.append({"text": "拜访知情人，尝试从交涉中撬开缺口", "intent": "negotiate", "target": None, "risk": "medium"})
        else:
            candidates.append({"text": f"围绕“{objective}”继续摸排线索", "intent": "explore", "target": None, "risk": "medium"})

        candidates.append({"text": "向附近人物打听异动与流言", "intent": "query", "target": None, "risk": "low"})
        candidates.append({"text": f"转去{location}外围侦察，看看是否有新痕迹", "intent": "explore", "target": None, "risk": "medium"})
        candidates.append({"text": "试着与可疑人物周旋，套出更多消息", "intent": "negotiate", "target": None, "risk": "medium"})
        candidates.append({"text": "主动挑一场短兵相接，逼出隐藏对手", "intent": "combat", "target": None, "risk": "high"})

        if health <= 35 or stamina <= 25:
            candidates.append({"text": "立刻撤到安全点疗伤调息，保住下一轮爆发", "intent": "rest", "target": None, "risk": "low"})
        else:
            candidates.append({"text": "暂时收线，整备装备并复盘情报再出手", "intent": "rest", "target": None, "risk": "low"})

        usable_items = self._inventory_usable_items(inventory)
        for item in usable_items[:1]:
            candidates.append({"text": f"使用{item}稳定状态后再行动", "intent": "use_item", "target": item, "risk": "low"})

        if side_quests:
            q = str(side_quests[seed % len(side_quests)]).strip()
            if q:
                candidates.append(
                    {
                        "text": f"顺手追查支线“{q}”，看看能否反向带出主线消息",
                        "intent": "explore",
                        "target": None,
                        "risk": "medium",
                    }
                )

        if stage_idx >= 5:
            candidates.append(
                {
                    "text": "直闯对手外圈防线，逼其提前暴露底牌",
                    "intent": "combat",
                    "target": None,
                    "risk": "high",
                }
            )

        options = self._unique_options(candidates)
        for i, opt in enumerate(options, start=1):
            opt["id"] = f"o{i}"

        if len(options) < 4:
            fallback = [
                {"id": "ox1", "text": "向老线人补一轮交叉求证", "intent": "query", "target": None, "risk": "low"},
                {"id": "ox2", "text": "沿屋脊与后巷双线侦察，寻找突破口", "intent": "explore", "target": None, "risk": "medium"},
                {"id": "ox3", "text": "以小代价试探敌方反应，再决定是否强攻", "intent": "combat", "target": None, "risk": "medium"},
            ]
            options = self._unique_options(options + fallback)
            for i, opt in enumerate(options, start=1):
                opt["id"] = f"o{i}"

        return options[:4]

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = self._extract_payload(messages)
        turn = {
            "narration": self._build_narration(payload),
            "options": self._build_options(payload),
        }
        self.last_meta = {"mode": "offline", "status": "ok"}
        return json.dumps(turn, ensure_ascii=False)


def build_client(
    *,
    base_url: str,
    api_key: Optional[str],
    model: str,
    temperature: float,
    top_p: float,
    max_tokens: int,
) -> LLMClient:
    if not api_key:
        return OfflineLLMClient()
    return LLMClient(
        ChatParams(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=temperature,
            top_p=top_p,
            max_tokens=max_tokens,
        )
    )

