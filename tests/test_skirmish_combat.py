from __future__ import annotations

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
