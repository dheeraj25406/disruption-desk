from app.db import Base,engine,SessionLocal
from app.seed import seed
from app.graph.workflow import run_workflow

def setup_module(): Base.metadata.create_all(engine);seed()
def test_regression_grounded_report():
    db=SessionLocal()
    try:
        rid,report,trace,failure=run_workflow(db,"INDEMO0025",lambda *args:"Synthetic evidence shows a 30 minute connection below the 60 minute policy minimum.")
        assert failure is None
        assert report["run_id"]==rid and report["policy_decision"]=="escalate"
        assert report["workflow_status"]=="escalated"
        assert report["connection_assessments"][0]["minutes"]==30
        assert report["candidate_alternatives"]==[]
        assert report["human_review_required"]
        assert all(x["status"]=="completed" for x in trace)
    finally:db.close()
def test_provider_failure_propagates():
    db=SessionLocal()
    try:
        def fail(*args): raise RuntimeError("provider unavailable")
        rid,report,trace,failure=run_workflow(db,"INDEMO0025",fail)
        assert report is None and failure["category"]=="provider"
        assert trace[-1]["status"]=="failed"
    finally:db.close()

def test_all_fifty_synthetic_cases_complete_with_mocked_interpreter():
    db=SessionLocal()
    try:
        from app.models import Case
        rows=db.query(Case).order_by(Case.id).all()
        assert len(rows)==50
        explain=lambda *args:"Mock interpretation using only provided synthetic facts and deterministic policy."
        for row in rows:
            rid,report,trace,failure=run_workflow(db,row.id,explain)
            assert failure is None, row.id
            assert report["case_id"]==row.id
            assert report["run_id"]==rid
            assert report["workflow_status"] in {"completed","escalated","awaiting_human_review"}
            assert all(candidate["airline"] in {"Air India","IndiGo","Air India Express","Akasa Air","SpiceJet"} for candidate in report["candidate_alternatives"])
            assert trace[-1]["agent"]=="Orchestrator"
    finally:db.close()
