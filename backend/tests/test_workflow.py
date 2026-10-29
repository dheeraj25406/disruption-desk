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

def test_live_schedule_workflow_uses_registered_provider_tool_and_labels_sources():
    from app.services.airlabs import normalize_flight
    record={"id":"provider-1","flight_date":"2026-10-30","status":"scheduled",
      "airline_name":"Example Air","flight_iata":"EX102",
      "dep_iata":"DEL","arr_iata":"BLR","dep_time_utc":"2026-10-30T05:30:00Z",
      "arr_time_utc":"2026-10-30T08:00:00Z"}
    class MockScheduleClient:
      def search_schedules(self,origin,destination,flight_date):
        assert (origin,destination,flight_date)==("DEL","BLR","2026-10-30")
        return [normalize_flight(record,flight_date)]
    db=SessionLocal()
    try:
        captured={}
        def explain(case,decision,reasons,candidates):
            captured.update(case=case,candidates=candidates,decision=decision)
            return "A simulated cancellation has a provider-listed schedule candidate; an operator must check seats."
        rid,report,trace,failure=run_workflow(db,"INDEMO0001",explain,alternative_source="airlabs",flight_date="2026-10-30",flight_client=MockScheduleClient())
        assert failure is None
        assert report["run_id"]==rid
        assert report["candidate_alternatives"][0]["source"]=="airlabs"
        assert report["candidate_alternatives"][0]["availability_confirmed"] is False
        assert report["evidence"][0]["source"]=="training_case_database"
        assert report["evidence"][1]["source"]=="airlabs"
        assert any(x.get("tool")=="search_airlabs_alternatives" for x in trace)
        assert captured["case"]["disruption_source"]=="simulated_training_case"
        assert captured["candidates"][0]["flight"]=="EX102"
        assert report["human_review_required"] is True
        assert report["workflow_status"]=="awaiting_human_review"
    finally:db.close()

def test_live_recovery_workflow_uses_published_route_patterns_as_distinct_candidates():
    db=SessionLocal()
    try:
        class RoutePatternClient:
            def search_alternatives(self,origin,destination,flight_date):
                assert (origin,destination,flight_date)==("DEL","BLR","2026-10-30")
                rows=[]
                for index,departure_hour in enumerate((10,11,12,13)):
                    departure=f"2026-10-30T{departure_hour}:30:00"; arrival=f"2026-10-30T{departure_hour+2}:15:00"
                    rows.append({"provider":"airlabs","schedule_basis":"published_route_pattern","flight_date":flight_date,
                      "flight_number":f"6E20{index+1}","flight":f"6E20{index+1}","airline":"IndiGo","origin":origin,"destination":destination,
                      "scheduled_departure":departure,"scheduled_arrival":arrival,"departure":departure,"arrival":arrival,
                      "departure_local_time":departure[-8:-3],"arrival_local_time":arrival[-8:-3],"operating_days":["fri"],
                      "source":"airlabs_route_pattern","availability_confirmed":False})
                rows.insert(1,{**rows[0],"flight_number":"AI9201","flight":"AI9201","airline":"Air India"})
                return rows,"published_route_pattern"
        rid,report,trace,failure=run_workflow(db,"INDEMO0001",lambda *args:"AirLabs route pattern candidates fit the route and clock time; an operator must verify live operation and inventory.",alternative_source="airlabs",flight_date="2026-10-30",flight_client=RoutePatternClient())
        assert failure is None
        candidate=report["candidate_alternatives"][0]
        assert candidate["flight"]=="6E201" and candidate["source"]=="airlabs_route_pattern"
        assert candidate["schedule_basis"]=="published_route_pattern"
        assert candidate["eligible"] is True
        assert candidate["availability_confirmed"] is False
        assert report["best_candidate_flight"]=="6E201"
        assert len(report["candidate_alternatives"])==3
        assert sum(item["is_best_match"] for item in report["candidate_alternatives"])==1
        assert [item["flight"] for item in report["candidate_alternatives"]]==["6E201","6E202","6E203"]
        assert report["human_review_required"] is True
        assert "not date-specific live schedules" in " ".join(report["limitations"])
        assert any("published_route_pattern" in step.get("result_summary","") for step in trace)
    finally:db.close()
