from storyweaver.engine import GameEngine


def test_stage_timeout_triggers_game_over() -> None:
    e = GameEngine()
    st = e.state

    # Force timeout for current stage without mutating stage config.
    st.flags["stage_enter_turn"] = 0
    st.flags["turn"] = 100

    turn = e.step("探索四周")
    assert bool(st.flags.get("game_over")) is True
    assert "本局失败" in turn["narration"]
    assert any(str(o.get("text")) == "/reset" for o in turn["options"])


def test_stage_timeout_triggers_when_limit_is_reached() -> None:
    e = GameEngine()
    st = e.state

    # Stage 0 timeout budget is 12. The next step increments turn first, so 11
    # here means the step reaches the limit exactly.
    st.flags["stage_enter_turn"] = 0
    st.flags["turn"] = 11

    turn = e.step("探索四周")
    assert bool(st.flags.get("game_over")) is True
    assert "超过时限 12 回合" in str(st.flags.get("game_over_reason") or "")
    assert "本局失败" in turn["narration"]


def test_game_over_blocks_normal_progress() -> None:
    e = GameEngine()
    st = e.state
    st.flags["game_over"] = True
    st.flags["game_over_reason"] = "测试失败"

    turn = e.step("打听消息")
    assert "本局失败" in turn["narration"]
    assert bool(turn["debug"].get("game_over")) is True


def test_failure_epilogue_is_generated_and_cached() -> None:
    class _MockClient:
        def chat(self, messages):
            return '{"narration":"你败于迟疑，旧盟尽散，唯余孤灯照雪。","options":[{"id":"o1","text":"收拾行囊","intent":"rest","target":null,"risk":"low"},{"id":"o2","text":"沉默离去","intent":"travel","target":null,"risk":"low"}]}'

    e = GameEngine()
    e.client = _MockClient()
    st = e.state
    st.flags['stage_enter_turn'] = 0
    st.flags['turn'] = 100

    turn = e.step('探索四周')
    assert '你败于迟疑' in turn['narration']
    assert bool(st.flags.get('game_over_epilogue'))


def test_stage_guidance_marks_preferred_options() -> None:
    e = GameEngine()
    # stage 0 prefers query / explore / negotiate
    e.state.flags["stage_idx"] = 0
    raw = [
        {"id": "o1", "text": "先去巡街", "intent": "explore", "target": None, "risk": "low"},
        {"id": "o2", "text": "找掌柜打听", "intent": "query", "target": None, "risk": "low"},
        {"id": "o3", "text": "上前交涉", "intent": "negotiate", "target": None, "risk": "medium"},
    ]
    guided = e._apply_stage_guidance_to_options(raw)
    assert str(guided[0].get("intent")) in {"query", "explore", "negotiate"}
    assert str(guided[0].get("hint", "")) == "mainline"
