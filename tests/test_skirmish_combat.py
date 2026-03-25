from __future__ import annotations

import json

from storyweaver.combat import Enemy
from storyweaver.engine import GameEngine
from storyweaver.llm_client import OfflineLLMClient


def test_combat_action_starts_skirmish_scene() -> None:
    e = GameEngine()
    e.state.flags["stage_idx"] = 1
    turn = e.step("主动出手战斗")
    assert bool(turn.get("debug", {}).get("skirmish")) is True
    assert e.is_skirmish_active() is True
    assert "技能按钮" in str(turn.get("narration") or "")
    sk = e._skirmish_state()
    assert str(sk.get("faction") or "")
    assert str(sk.get("origin") or "")
    assert isinstance(e.state.known_facts.get("enemy_factions_seen"), list)


def test_skirmish_victory_returns_followup_options() -> None:
    e = GameEngine()
    enemy = Enemy(
        "断桥伏击手",
        12,
        8,
        2,
        "追魂",
        12,
        2,
        faction="断桥伏兵",
        origin="断桥渡口",
        clue_text="伏击手掉出一枚镖局旧印，说明内部有人通敌。",
        clue_fact_key="escort_guild_infiltrated",
        clue_fact_value="True",
        evidence_item="镖局信物",
    )
    e._start_skirmish(enemy)
    sk = e._skirmish_state()
    sk["hp"] = 1
    result = e.skirmish_skill_action("轻功")
    assert result.get("debug", {}).get("skirmish") == "won"
    assert e.is_skirmish_active() is False
    assert len(result.get("options") or []) >= 1
    memory = e.state.flags.get("story_memory") or []
    assert memory
    assert "遭遇战" in str(memory[-1].get("action") or "")
    assert any(str(opt.get("intent") or "") in {"explore", "query", "travel", "rest", "combat", "negotiate"} for opt in (result.get("options") or []))
    assert bool(e.state.known_facts.get("escort_guild_infiltrated")) is True
    assert bool(e.state.known_facts.get("escort_token")) is True
    assert "镖局信物" in (e.state.known_facts.get("combat_evidence") or [])


def test_chapter_two_offered_combat_option_starts_skirmish() -> None:
    e = GameEngine()
    e.client = OfflineLLMClient()
    e.state.flags["stage_idx"] = 1
    e.state.flags["stage_enter_turn"] = 0
    result = e.step("观察山道伏兵动静")

    combat_option = next(opt for opt in (result.get("options") or []) if opt.get("intent") == "combat")
    combat_result = e.step(str(combat_option.get("text") or ""))

    assert combat_result.get("debug", {}).get("skirmish") == "started"
    assert e.is_skirmish_active() is True


def test_skirmish_defeat_triggers_game_over() -> None:
    e = GameEngine()
    enemy = Enemy(
        "黑松会执事",
        80,
        999,
        10,
        "毒刃",
        20,
        3,
        faction="黑松会",
        origin="黑松岭内堂",
    )
    e._start_skirmish(enemy)
    e.state.health = 1
    e.state.stamina = 1

    result = e.skirmish_skill_action("轻功")

    assert bool(e.state.flags.get("game_over")) is True
    assert e.state.health == 0
    assert e.is_skirmish_active() is False
    assert result.get("debug", {}).get("skirmish") == "lost"
    assert bool(result.get("debug", {}).get("game_over")) is True
    assert "本局失败" in str(result.get("narration") or "")
    assert any(str(opt.get("text") or "") == "/reset" for opt in (result.get("options") or []))


def test_skirmish_defeat_uses_llm_failure_context() -> None:
    captured: list[list[dict[str, str]]] = []

    class _MockClient:
        def chat(self, messages):
            captured.append(messages)
            return "你被黑松会执事一式拖刀反掠斩开护身气劲，血洒荒径，就此殒命。"

    e = GameEngine()
    e.client = _MockClient()
    enemy = Enemy(
        "黑松会执事",
        80,
        999,
        10,
        "毒刃",
        20,
        3,
        faction="黑松会",
        origin="黑松岭内堂",
    )
    e._start_skirmish(enemy)
    e.state.health = 1
    e.state.stamina = 1

    result = e.skirmish_skill_action("轻功")

    assert "血洒荒径，就此殒命" in str(result.get("narration") or "")
    assert captured
    payload = json.loads(captured[-1][1]["content"])
    assert payload["failure_kind"] == "skirmish"
    assert payload["combat_context"]["enemy_name"] == "黑松会执事"
    assert payload["combat_context"]["enemy_style"] == "毒刃"
    assert payload["combat_context"]["finisher"]
    assert any("你受到" in line for line in payload["combat_context"]["combat_log"])


def test_boss_defeat_triggers_game_over() -> None:
    e = GameEngine()
    e.state.flags["stage_idx"] = 7
    ok, _ = e.start_boss_fight()
    assert ok is True
    e.state.health = 1
    e.state.stamina = 1

    result = e.boss_skill_action("轻功")

    assert bool(e.state.flags.get("game_over")) is True
    assert e.state.health == 0
    assert e.is_boss_active() is False
    assert result.get("debug", {}).get("boss") == "lost"
    assert bool(result.get("debug", {}).get("game_over")) is True
    assert "本局失败" in str(result.get("narration") or "")
    assert any(str(opt.get("text") or "") == "/reset" for opt in (result.get("options") or []))
