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

def test_route_pattern_candidate_is_timing_checked_but_never_claims_live_status_or_inventory():
    from app.policy.engine import assess_provider_alternative
    case={"origin":"DEL","destination":"BLR","legs":[{"departure":"2026-10-30T08:00:00"}]}
    candidate={"flight":"6E201","origin":"DEL","destination":"BLR","departure":"2026-10-30T10:30:00","arrival":"2026-10-30T13:15:00","source":"airlabs_route_pattern","schedule_basis":"published_route_pattern","availability_confirmed":False}
    result=assess_provider_alternative(case,candidate)
    assert result["eligible"] is True
    assert "recurring route pattern" in result["reason"]
    assert result["availability_confirmed"] is False
    too_early=assess_provider_alternative(case,{**candidate,"departure":"2026-10-30T07:00:00"})
    assert too_early["eligible"] is False
    assert "departs_before_disrupted_itinerary" in too_early["eligibility_reason_codes"]

def test_provider_ranking_shortlists_three_distinct_eligible_schedule_slots():
    from app.policy.engine import rank_provider_alternatives
    def row(flight,departure,arrival,eligible=True):
        return {"flight":flight,"departure":departure,"arrival":arrival,"eligible":eligible}
    ranked=rank_provider_alternatives([
        row("6E500","2026-10-30T10:00:00","2026-10-30T12:00:00"),
        row("AI500","2026-10-30T10:00:00","2026-10-30T12:00:00"),
        row("6E501","2026-10-30T11:00:00","2026-10-30T13:00:00"),
        row("6E502","2026-10-30T12:00:00","2026-10-30T14:00:00"),
        row("6E503","2026-10-30T13:00:00","2026-10-30T15:00:00"),
        row("6E499","2026-10-30T09:00:00","2026-10-30T11:00:00",False),
    ])
    assert [x["flight"] for x in ranked]==["6E500","6E501","6E502"]
    assert ranked[0]["is_best_match"] is True
    assert ranked[0]["shortlist_rank"]==1
    assert all(x["eligible"] for x in ranked)

def test_human_review_is_separate_from_a_blocking_policy_decision():
    legs=[{"origin":"DEL","destination":"BLR","departure":"2026-10-30T08:00:00+05:30","arrival":"2026-10-30T10:00:00+05:30"}]
    result=evaluate(legs,True,True,1)
    assert result.decision=="proceed"
    assert result.human_review_required is True
    assert result.reason_codes==["itinerary_connection_requires_review"]

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
