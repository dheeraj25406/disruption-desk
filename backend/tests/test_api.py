from fastapi.testclient import TestClient
from app.main import app

def test_health_and_cases():
    with TestClient(app) as c:
        assert c.get("/health").status_code==200
        cases=c.get("/api/cases").json()
        assert len(cases)>=6
        assert c.get("/api/cases/INDEMO0025/policy").json()["connections"][0]["minutes"]==30
        assert c.get("/api/cases/NOT-REAL").status_code==404

def test_case_queue_returns_triage_fields_in_priority_order():
    c=TestClient(app)
    rows=c.get('/api/cases').json()
    assert rows[0]['priority']=='urgent'
    assert rows[0]['action_by'].startswith('Now')
    assert all('attention_summary' in row for row in rows)
    assert len(rows)==50
