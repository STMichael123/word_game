from __future__ import annotations

from storyweaver.engine import GameEngine


class _MockClient:
    last_meta = {"mode": "online", "status": "ok"}

    def chat(self, messages):
        return '{"narration":"你顺着新得的线索望向雁回山道，意识到接下来已不是零散打听，而是护送与截杀并行的险局。","options":[{"id":"o1","text":"沿山道暗访伏兵踪迹","intent":"explore","target":null,"risk":"medium"},{"id":"o2","text":"先去接应镖师队伍","intent":"travel","target":null,"risk":"medium"}]}'


def test_opening_scene_contains_background_goal_and_first_chapter() -> None:
    e = GameEngine()
    turn = e.opening_scene()
    msgs = turn.get("system_messages") or []
    joined = "\n".join(str(x) for x in msgs)
    assert "江湖背景" in joined
    assert "终局目标" in joined
    assert "第1章·青石镇异闻" in joined
    assert len(turn.get("options") or []) >= 3


def test_stage_transition_emits_chapter_intro_message() -> None:
    e = GameEngine()
    e.client = _MockClient()
    e.state.flags["progress"] = 6
    e.state.flags["objective_counters"] = {
        "query_count": 2,
        "combat_win": 0,
        "negotiate_win": 0,
        "explore_count": 0,
    }
    turn = e.step("继续打听黑松会消息")
    msgs = turn.get("system_messages") or []
    joined = "\n".join(str(x) for x in msgs)
    assert "第2章·雁回山路" in joined
    assert "本章冲突" in joined
