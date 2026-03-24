from storyweaver.engine import GameEngine


def test_all_endings_reachable() -> None:
    e = GameEngine()
    st = e.state

    st.martial_level = 8
    st.inner_power = 130
    assert e._determine_ending() == '武道极境'

    st.martial_level = 2
    st.inner_power = 20
    st.reputation = 60
    st.flags['npc_registry'] = {
        '甲': {'relation': 6},
        '乙': {'relation': 7},
        '丙': {'relation': 8},
    }
    assert e._determine_ending() == '义满江湖'

    st.reputation = 10
    st.silver = 220
    st.sect = '青云门'
    assert e._determine_ending() == '财富权谋'

    st.silver = 20
    st.sect = None
    st.known_facts['black_wood_token'] = True
    st.flags['stage_idx'] = 6
    assert e._determine_ending() == '解谜真相'

    st.known_facts['black_wood_token'] = False
    st.reputation = 0
    st.flags['npc_registry'] = {}
    assert e._determine_ending() == '孤侠天涯'
