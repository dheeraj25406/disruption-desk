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

def test_aviation_status_endpoint_exposes_plan_but_never_key():
    c=TestClient(app)
    response=c.get('/api/aviation/status')
    assert response.status_code==200
    body=response.json()
    assert body['provider']=='AirLabs'
    assert body['credentials_status'] in {'configured_unverified','missing'}
    assert body['account_plan']=='unknown'
    assert body['monthly_request_limit'] is None
    assert body['live_status_access'] is True
    assert body['future_schedules_access'] is True
    assert 'api_key' not in body and 'access_key' not in body

def test_live_schedules_use_provider_and_never_return_training_fallback(monkeypatch):
    from app.services.airlabs import AirLabsClient
    monkeypatch.setattr(AirLabsClient,'search_schedules',lambda self,*args:[])
    monkeypatch.setattr(AirLabsClient,'search_route_patterns',lambda self,*args:[])
    c=TestClient(app)
    response=c.get('/api/cases/INDEMO0025/live-alternatives')
    assert response.status_code==200
    assert response.json()['source']=='airlabs'
    assert response.json()['records']==[]
    assert response.json()['availability_confirmed'] is False

def test_flight_status_uses_provider_for_requested_date_on_free_plan(monkeypatch):
    from app.services.airlabs import AirLabsClient
    monkeypatch.setattr(AirLabsClient,'flight_status',lambda self,*args:[])
    c=TestClient(app)
    response=c.get('/api/aviation/flight-status',params={'flight_number':'AI 101','flight_date':'2026-10-30'})
    assert response.status_code==200
    assert response.json()['source']=='airlabs'
    assert response.json()['flight_date']=='2026-10-30'
    assert response.json()['records']==[]

def test_standard_analyze_endpoint_uses_airlabs_recovery_not_training_alternatives(monkeypatch):
    from uuid import uuid4
    import app.api.routes as routes
    captured={};run_id=str(uuid4());recommendation_id=str(uuid4())
    def fake_workflow(db,case_id,**kwargs):
        captured.update(case_id=case_id,**kwargs)
        return run_id,{'run_id':run_id,'case_id':case_id,'workflow_status':'awaiting_human_review','human_review_required':True,'recommendation_id':recommendation_id,'policy_decision':'proceed'},[],None
    monkeypatch.setattr(routes,'run_workflow',fake_workflow)
    response=TestClient(app).post('/api/cases/INDEMO0001/analyze')
    assert response.status_code==200
    assert captured['alternative_source']=='airlabs'
    assert captured['flight_date']=='2026-10-30'
    assert response.json()['workflow_status']=='awaiting_human_review'
