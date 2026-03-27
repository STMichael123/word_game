from storyweaver.engine import GameEngine
from storyweaver.llm_client import OfflineLLMClient


def test_stage_five_explore_reveals_alliance_route_fact() -> None:
    e = GameEngine()
    e.client = OfflineLLMClient()
    st = e.state

    st.flags["stage_idx"] = 4
    st.flags["progress"] = 38
    st.flags["stage_enter_turn"] = 0
    st.location = "黑松岭"
    st.last_options = e._current_stage_scene_options(limit=4)

    e.step("潜进黑松岭外圈查顾长风被囚方位")

    assert bool(st.known_facts.get("gu_changfeng_captive")) is True
    assert bool(st.known_facts.get("leader_heading_to_alliance")) is True


def test_stage_five_can_advance_without_black_wood_token_via_explore_route() -> None:
    e = GameEngine()
    e.client = OfflineLLMClient()
    st = e.state

    st.flags["stage_idx"] = 4
    st.flags["progress"] = 38
    st.flags["stage_enter_turn"] = 0
    st.location = "黑松岭"
    st.last_options = e._current_stage_scene_options(limit=4)

    e.step("潜进黑松岭外圈查顾长风被囚方位")
    e.step("潜进黑松岭外圈查顾长风被囚方位")
    e.step("潜进黑松岭外圈查顾长风被囚方位")

    assert int(st.flags.get("stage_idx", 0)) == 5
    assert bool(st.flags.get("chapter_5_done")) is True