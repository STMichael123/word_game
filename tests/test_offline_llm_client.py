from __future__ import annotations

import json

from storyweaver.llm_client import OfflineLLMClient


def test_offline_client_builds_turn_without_runtime_error() -> None:
    client = OfflineLLMClient()
    payload = {
        "player_action": "【主线建议】向街坊酒客继续打听",
        "state": {
            "day": 3,
            "location": "古寺",
            "stats": {"health": 90, "stamina": 80},
            "active_side_quests": ["夜巡断案"],
        },
        "story_stage": {
            "index": 1,
            "title": "青石镇异闻",
            "objective": "护送镖师穿过山道并击退劫匪",
        },
        "current_chapter_arc": {
            "intro": "你已追到雁回山路，镖队与伏兵之间只剩一段险坡。",
            "conflict": "你必须在护送镖师与逼出内鬼之间同时周旋。",
            "significance": "这一章决定你能否真正摸到黑松会伸进镖局的手。",
        },
        "chapter_progress_narrative": "本章目标是：护送镖师穿过山道并击退劫匪。当前关键进度：取胜战斗 1/1。",
        "time_context": {"day": 3, "phase": "夜幕", "label": "第3日·夜幕", "memory_timestamp": "第3日下午"},
        "recent_fact_timeline": ["第2回：你夺得关键证物：镖局信物 这意味着这说明镖局内部可能有人通敌"],
        "sim_result": {
            "detail_lines": ["你从酒客口中探得山道劫匪与黑松会有关。"],
            "notes": ["【主线推进】青石镇异闻 完成"],
            "encounter": {"kind": "combat"},
        },
        "story_so_far": [{"memory_timestamp": "第2日上午", "memory_index": "收集到关键江湖消息", "summary": "你收集到关键江湖消息"}],
        "npcs_known": [{"name": "沈清川"}],
    }
    txt = client.chat([{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
    obj = json.loads(txt)
    assert isinstance(obj.get("narration"), str) and obj["narration"]
    assert "【主线建议】" not in obj["narration"]
    assert len(obj["narration"]) >= 120
    assert "第3日下午" in obj["narration"]
    assert "收集到关键江湖消息" in obj["narration"]
    assert "黑松会" in obj["narration"]
    assert "镖局信物" in obj["narration"]
    assert "护送镖师穿过山道并击退劫匪" in obj["narration"]
    options = obj.get("options")
    assert isinstance(options, list) and len(options) >= 3
    assert all(str(opt.get("intent")) in {"explore", "combat", "query", "negotiate", "travel", "rest", "use_item"} for opt in options)


def test_offline_narration_failed_item_use_not_forced_to_mainline() -> None:
    client = OfflineLLMClient()
    payload = {
        "player_action": "使用上品止血散",
        "state": {
            "day": 4,
            "location": "古寺残钟",
            "stats": {"health": 78, "stamina": 73},
        },
        "story_stage": {
            "index": 1,
            "title": "青石镇异闻",
            "objective": "打听三条关于黑松会的情报",
        },
        "sim_result": {
            "delta": {"progress": 0},
            "detail_lines": ["你翻找包裹，却没找到合适之物。"],
            "notes": [],
            "encounter": {"kind": "npc"},
        },
    }
    txt = client.chat([{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}])
    obj = json.loads(txt)
    nar = str(obj.get("narration") or "")
    assert "没找到合适之物" in nar
    assert "下一步的关键仍系于" not in nar
