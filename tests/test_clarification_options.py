from __future__ import annotations

from storyweaver.engine import GameEngine


def test_use_item_clarification_uses_inventory_context() -> None:
    e = GameEngine()
    e.state.inventory = ["粗布衣", "竹笛"]
    turn = e.step("使用")
    assert bool(turn.get("debug", {}).get("clarify")) is True
    opts = turn.get("options") or []
    texts = [str(o.get("text") or "") for o in opts]
    joined = " ".join(texts)
    assert "上品止血散" not in joined
    assert any(("查看背包" in t) or ("调息" in t) or ("打听" in t) for t in texts)
