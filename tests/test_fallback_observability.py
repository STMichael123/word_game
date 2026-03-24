from storyweaver.engine import GameEngine


class _BrokenClient:
    def __init__(self) -> None:
        self.last_meta = {'mode': 'offline-fallback', 'error': 'MockError'}

    def chat(self, messages):
        return 'NOT_JSON'


def test_fallback_observability_fields_present() -> None:
    e = GameEngine()
    e.client = _BrokenClient()
    turn = e.step('探索四周')
    assert 'llm_mode' in turn['debug']
    assert turn['debug']['llm_mode'] == 'offline-fallback'
    assert 'llm_fallback_reason' in turn['debug']
    assert any('在线叙事模型当前不可用' in msg for msg in turn.get('system_messages', []))
    assert int(e.state.flags.get('llm_parse_fail_count', 0)) >= 1
