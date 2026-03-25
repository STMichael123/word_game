from fastapi.testclient import TestClient

from app_web import app


def test_api_smoke_submit_boss_export() -> None:
    c = TestClient(app)

    landing = c.get('/')
    assert landing.status_code == 200
    assert '江湖背景' in landing.text
    assert '终局目标' in landing.text
    assert 'resetDialogSurface' in landing.text

    llm_status = c.get('/api/llm/status')
    assert llm_status.status_code == 200
    assert 'configured' in llm_status.json()
    assert 'model' in llm_status.json()

    r1 = c.post('/api/submit', json={'text': '探索四周'})
    assert r1.status_code == 200
    assert 'state_data' in r1.json()
    assert 'scene_mode' in r1.json()
    assert 'time_label' in r1.json()['state_data']
    assert 'memory_preview' in r1.json()['state_data']

    # Boss may be locked at early game, but endpoint should be stable.
    r2 = c.post('/api/boss/start', json={})
    assert r2.status_code == 200
    assert 'narration' in r2.json()

    r3 = c.post('/api/export', json={})
    assert r3.status_code == 200
    assert 'story_text' in r3.json()


def test_skirmish_skill_api_returns_debug() -> None:
    c = TestClient(app)

    start = c.post('/api/submit', json={'text': '主动出手战斗'})
    assert start.status_code == 200
    assert start.json()['scene_mode'] == 'skirmish'

    skill = c.post('/api/skirmish/skill', json={'skill': '轻功'})
    assert skill.status_code == 200
    payload = skill.json()
    assert 'debug' in payload
    assert isinstance(payload['debug'], dict)
