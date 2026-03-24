from fastapi.testclient import TestClient

from app_web import app


def test_session_isolation_between_clients() -> None:
    c1 = TestClient(app)
    c2 = TestClient(app)

    r1 = c1.post('/api/submit', json={'text': '探索四周'})
    assert r1.status_code == 200
    d1 = r1.json()['state_data']

    r2 = c2.post('/api/submit', json={'text': '/reset'})
    assert r2.status_code == 200
    d2 = r2.json()['state_data']

    # A second action on client1 should continue its own timeline, not client2's reset timeline.
    r1b = c1.post('/api/submit', json={'text': '打听消息'})
    assert r1b.status_code == 200
    d1b = r1b.json()['state_data']

    assert d1b['turn'] >= d1['turn']
    assert d1b['turn'] != d2['turn']
