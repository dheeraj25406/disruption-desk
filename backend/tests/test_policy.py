from app.policy.engine import evaluate
from app.seed import dt

def test_regression_connection_and_policy():
    legs=[{"arrival":dt(30,11)},{"departure":dt(30,11,30)}]
    result=evaluate(legs,True,True,0)
    assert result.connections[0]["minutes"]==30
    assert result.connections[0]["minimum_minutes"]==60
    assert result.decision=="escalate"
    assert "below_minimum_connection_buffer" in result.reason_codes
    assert result.human_review_required

def test_missing_evidence_no_candidates():
    result=evaluate([],False,False,0)
    assert result.decision=="escalate"
    assert {"missing_required_evidence","no_eligible_alternatives"}<=set(result.reason_codes)

def test_policy_ineligible():
    assert evaluate([],True,False,1).decision=="proceed"

def test_attention_queue_prioritizes_connection_and_review_cases():
    from app.db import SessionLocal
    from app.models import Case
    from app.services.attention import classify_attention
    db=SessionLocal()
    try:
        urgent=classify_attention(db.get(Case,"INDEMO0025"))
        assert urgent["priority"]=="urgent"
        assert "Now" in urgent["action_by"]
        evidence=classify_attention(db.get(Case,"INDEMO0004"))
        assert evidence["priority"]=="review"
        assert evidence["action_by"]=="Before recovery advice"
        review=classify_attention(db.get(Case,"INDEMO0006"))
        assert review["priority"]=="review"
        assert review["action_by"]=="Within 30 minutes"
    finally:db.close()
