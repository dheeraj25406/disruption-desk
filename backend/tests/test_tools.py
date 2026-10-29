import pytest
from pydantic import ValidationError
from app.db import Base,engine,SessionLocal
from app.seed import seed
from app.tools.registry import build_tools

def setup_module(): Base.metadata.create_all(engine);seed()
def test_registered_data_tools_and_validation():
    db=SessionLocal()
    try:
        registry=build_tools(db)
        case=registry["get_disruption_case"].invoke({"case_id":"INDEMO0025"})
        assert case["flight"]=="DEMO-AI-2125"
        assert registry["search_synthetic_alternatives"].invoke({"case_id":"INDEMO0025"})==[]
        with pytest.raises(ValidationError): registry["get_disruption_case"].invoke({"case_id":""})
        with pytest.raises(ValueError,match="unknown_case"):
            registry["get_disruption_case"].invoke({"case_id":"unknown"})
        assert "get_unregistered_tool" not in registry
    finally: db.close()
def test_incomplete_evidence_skips_recovery_tool():
    from app.graph.workflow import run_workflow
    db=SessionLocal()
    try:
        rid,report,trace,failure=run_workflow(db,"INDEMO0004",lambda *args:"Incomplete evidence requires operator clarification.")
        assert failure is None
        assert "missing_required_evidence" in report["reason_codes"]
        assert not any(x.get("tool")=="search_synthetic_alternatives" for x in trace)
        assert report["candidate_alternatives"]==[]
    finally: db.close()

def test_no_argument_policy_tool_and_candidate_eligibility():
    db=SessionLocal()
    try:
        registry=build_tools(db)
        rules=registry["get_policy_rules"].invoke({})
        assert rules["minimum_connection_minutes"]==60
        candidate=registry["evaluate_alternative_eligibility"].invoke({"case_id":"INDEMO0025","flight":"DEMO-ALT-X","origin":"BOM","destination":"GOI","departure":"2026-10-30T14:00:00+05:30","arrival":"2026-10-30T16:00:00+05:30","eligible":True,"reason":"seeded"})
        assert candidate["eligible"] is True
        invalid=registry["evaluate_alternative_eligibility"].invoke({"case_id":"INDEMO0025","flight":"DEMO-ALT-X","origin":"DEL","destination":"GOI","departure":"2026-10-30T16:00:00+05:30","arrival":"2026-10-30T14:00:00+05:30","eligible":True,"reason":"seeded"})
        assert invalid["eligible"] is False
    finally:db.close()
