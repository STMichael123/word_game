from __future__ import annotations

import json

from storyweaver.engine import GameEngine


def test_prompt_payload_includes_progress_and_fact_timeline() -> None:
    e = GameEngine()
    e.bind_memory_namespace("test_prompt_payload")
    e.state.flags["turn"] = 5
    e.state.flags["stage_idx"] = 1
    e.state.flags["objective_counters"] = {
        "query_count": 0,
        "combat_win": 1,
        "negotiate_win": 0,
        "explore_count": 0,
    }
    e.state.flags["fact_events"] = [
        {
            "turn": 4,
            "stage_idx": 1,
            "location": "雁回山道",
            "type": "evidence",
            "summary": "你夺得关键证物：镖局信物。",
            "significance": "这说明镖局内部可能有人通敌。",
            "refs": ["镖局信物"],
        }
    ]
    e.state.flags["story_memory"] = [
        {
            "turn": 3,
            "stage_idx": 0,
            "memory_timestamp": "第1日上午",
            "memory_index": "确认黑松会已在青石镇活动",
            "summary": "你确认黑松会已在青石镇活动。",
            "story_significance": "黑松会的触角并不只在街谈巷议里。",
            "chapter_goal_effect": "这一步让你得以离开青石镇，追向山路。",
        },
        {
            "turn": 5,
            "stage_idx": 1,
            "memory_timestamp": "第3日下午",
            "memory_index": "山道救下负伤镖师",
            "summary": "你在山道救下了一名负伤镖师。",
            "story_significance": "镖路并未完全断绝，仍有活口可问。",
            "chapter_goal_effect": "这一步直接服务于本章目标：护送镖师穿过山道并击退劫匪。",
        },
    ]
    e._sync_memory_document()

    payload = json.loads(
        e._build_prompt_payload(
            "追问镖师山道伏兵来路",
            {
                "delta": {"progress": 1},
                "detail_lines": ["你从镖师口中得知伏兵来自断桥一带。"],
                "notes": ["【主线推进】你已护住关键活口。"],
            },
        )
    )

    assert "chapter_progress_narrative" in payload
    assert "recent_fact_timeline" in payload
    assert "story_memory_current_arc" in payload
    assert payload["recent_fact_timeline"]
    assert "镖局信物" in "\n".join(payload["recent_fact_timeline"])
    assert payload["story_memory_current_arc"]
    assert all("memory_timestamp" in item and "memory_index" in item for item in payload["story_so_far"])
    assert any(str(item.get("memory_timestamp")) == "第3日下午" for item in payload["story_memory_current_arc"])
    assert any("护送镖师" in str(item.get("chapter_goal_effect") or "") for item in payload["story_memory_current_arc"])
    assert any("护住关键活口" in str(x) for x in payload["sim_result"]["notes"])
    assert payload["memory_doc"]["doc_id"] == "test_prompt_payload"


def test_record_story_memory_stores_timestamped_index_and_keeps_legacy_calls() -> None:
    e = GameEngine()
    e.bind_memory_namespace("test_record_story_memory")
    e.state.day = 2
    e.state.flags["time_phase"] = "夜幕"
    e.state.flags["turn"] = 7

    e._record_story_memory(
        action="查问码头脚夫",
        narration="你从脚夫口中得知有人夜里搬运封箱。",
        sim_result={"delta": {}, "detail_lines": ["你得知有人夜里搬运封箱。"]},
        stage_notes=[],
    )

    entry = e.state.flags["story_memory"][-1]
    assert entry["memory_timestamp"] == "第2日下午"
    assert entry["memory_index"] == "你得知有人夜里搬运封箱"
    assert entry["summary"] == entry["memory_index"]
    memory_doc = e.memory_document()
    assert memory_doc["timeline_memory"][-1]["memory_index"] == "你得知有人夜里搬运封箱"


def test_prompt_reads_external_memory_document_without_manual_save() -> None:
    e = GameEngine()
    e.bind_memory_namespace("test_external_memory_doc")
    e.state.flags["turn"] = 4
    e._record_story_memory(
        action="沿街追查货栈脚印",
        narration="你顺着货栈脚印摸到了后巷暗门。",
        sim_result={"delta": {"progress": 1}, "detail_lines": ["你顺着货栈脚印摸到了后巷暗门。"]},
        stage_notes=[],
    )
    e.state.flags["story_memory"] = []

    payload = json.loads(
        e._build_prompt_payload(
            "继续追查暗门后的去向",
            {"delta": {"progress": 1}, "detail_lines": ["你决定顺势追下去。"], "notes": []},
        )
    )

    assert payload["story_so_far"]
    assert payload["story_so_far"][-1]["memory_index"] == "你顺着货栈脚印摸到了后巷暗门"