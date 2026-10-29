from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from datetime import date
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime, timezone
from app.db import get_db,Base,engine
from app.seed import seed
from app.models import Case,Run,Recommendation
from app.graph.workflow import run_workflow
from app.policy.engine import evaluate
from app.agents.llm import ConfigurationError,ProviderError
from app.services.attention import classify_attention
from app.services.airlabs import AirLabsClient, FlightProviderError, FlightProviderQuotaError
from app.policy.engine import assess_provider_alternative
from app.tools.registry import build_tools
from zoneinfo import ZoneInfo
router=APIRouter()
@router.get("/health")
def health(): return {"status":"ok","data_mode":"simulated_cases_with_optional_airlabs_facts","model":"gemini-3.5-flash-lite"}

@router.get("/api/aviation/status")
def aviation_status():
    """Expose safe provider configuration metadata; never return the API key."""
    return AirLabsClient().status

def aviation_http_error(exc:FlightProviderError):
    code=429 if isinstance(exc,FlightProviderQuotaError) else (503 if exc.category=="configuration" else 502)
    return HTTPException(code,detail={"category":exc.category,"message":str(exc)})

@router.get("/api/aviation/flight-status")
def aviation_flight_status(
    flight_number:str=Query(min_length=2,max_length=16),
    flight_date:str|None=None,
):
    """Look up a real provider status for a real flight number; demo flight IDs are not looked up."""
    flight_date=flight_date or datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    try:
        flights=AirLabsClient().flight_status(flight_number,flight_date)
        return {"source":"airlabs","classification":"real provider flight status","retrieved_at":datetime.now(timezone.utc).isoformat(),"flight_number":flight_number.strip().upper(),"flight_date":flight_date,"records":[f.model_dump(mode="json") for f in flights],"message":"No matching flight status was returned." if not flights else None,"availability_confirmed":False}
    except FlightProviderError as exc:
        raise aviation_http_error(exc)
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc))

@router.get("/api/cases/{case_id}/live-alternatives")
def live_alternatives(case_id:str,flight_date:str|None=None,db:Session=Depends(get_db)):
    case_row=db.get(Case,case_id)
    if not case_row: raise HTTPException(404,"Unknown case ID")
    flight_date=flight_date or str(case_row.legs[0].get("departure",""))[:10]
    client=AirLabsClient()
    try:
        raw=build_tools(db,client)["search_airlabs_alternatives"].invoke({"case_id":case_id,"flight_date":flight_date})
        case_data={"origin":case_row.origin,"destination":case_row.destination,"legs":case_row.legs}
        assessed=[assess_provider_alternative(case_data,dict(x)) for x in raw]
        assessed.sort(key=lambda item:(not item["eligible"],item.get("departure","")))
        basis=assessed[0].get("schedule_basis") if assessed else None
        return {"case_id":case_id,"source":"airlabs","classification":"AirLabs flight schedule facts for a simulated disruption","schedule_basis":basis,"flight_date":flight_date,"origin":case_row.origin,"destination":case_row.destination,"records":assessed,"availability_confirmed":False,"message":("No matching AirLabs schedule or operating-day route pattern was returned." if not assessed else ("AirLabs recurring route patterns match the requested weekday; live operation and inventory are unconfirmed." if basis=="published_route_pattern" else "Schedule fit is not seat or fare availability."))}
    except FlightProviderError as exc:
        raise aviation_http_error(exc)
    except ValueError as exc:
        raise HTTPException(422,detail=str(exc))

class LiveRecoveryRequest(BaseModel):
    flight_date:date|None=None

@router.post("/api/cases/{case_id}/live-recovery")
def live_recovery(case_id:str,body:LiveRecoveryRequest|None=None,db:Session=Depends(get_db)):
    """Run the LangGraph Recovery Agent with real provider schedules and simulated case facts."""
    case_row=db.get(Case,case_id)
    if not case_row: raise HTTPException(404,"Unknown case ID")
    requested_date=(body.flight_date.isoformat() if body and body.flight_date else str(case_row.legs[0].get("departure",""))[:10])
    if not requested_date:
        raise HTTPException(422,detail="A flight_date is required when the itinerary has no departure date.")
    try:
        requested=date.fromisoformat(requested_date)
    except ValueError:
        raise HTTPException(422,detail="flight_date must use YYYY-MM-DD")
    if requested<datetime.now(ZoneInfo("Asia/Kolkata")).date():
        raise HTTPException(422,detail="Live recovery searches upcoming schedules only; historical dates are not accepted.")
    client=AirLabsClient()
    rid=str(uuid4())
    trace=[]
    try:
        rid,report,trace,failure=run_workflow(db,case_id,alternative_source="airlabs",flight_date=requested_date,flight_client=client)
        if failure:
            db.add(Run(id=rid,case_id=case_id,status="failed",report={"run_id":rid,"case_id":case_id,"workflow_status":"failed","error":failure},trace=trace));db.commit()
            raise HTTPException(503,detail={"run_id":rid,**failure})
        db.add(Run(id=rid,case_id=case_id,status=report["workflow_status"],report=report,trace=trace));db.commit()
        if report["human_review_required"]:
            db.add(Recommendation(id=report["recommendation_id"],run_id=rid));db.commit()
        return report
    except HTTPException:
        raise
    except FlightProviderError as exc:
        rid=str(uuid4()) if not trace else rid
        message=str(exc)
        trace=[{"step":1,"agent":"Recovery Agent","tool":"search_airlabs_alternatives","status":"failed","error_category":exc.category,"error_message":message}]
        db.add(Run(id=rid,case_id=case_id,status="failed",report={"run_id":rid,"case_id":case_id,"workflow_status":"failed","error":{"category":exc.category,"message":message}},trace=trace));db.commit()
        raise HTTPException(502,detail={"run_id":rid,"category":exc.category,"message":message})
@router.get("/api/cases")
def cases(db:Session=Depends(get_db)):
    rows=[]
    for c in db.query(Case).all():
        attention=classify_attention(c)
        rows.append({"case_id":c.id,"passenger_label":c.passenger_label,"affected_flight":c.flight,"airline":c.airline,"origin":c.origin,"destination":c.destination,"disruption_type":c.disruption,"status":"requires_review" if attention["human_review_required"] else "ready",**attention})
    return sorted(rows,key=lambda x:(x["priority_rank"],x["case_id"]))
@router.get("/api/cases/{case_id}")
def case(case_id:str,db:Session=Depends(get_db)):
    c=db.get(Case,case_id)
    if not c: raise HTTPException(404,"Unknown case ID")
    return {"case_id":c.id,"passenger_label":c.passenger_label,"affected_flight":c.flight,"airline":c.airline,"origin":c.origin,"destination":c.destination,"disruption_type":c.disruption,"disruption_detail":c.detail,"evidence_complete":c.evidence_complete,"human_review_configured":c.review_required,"legs":c.legs,"synthetic":True}
@router.get("/api/cases/{case_id}/itinerary")
def itinerary(case_id:str,db:Session=Depends(get_db)):
    c=db.get(Case,case_id)
    if not c: raise HTTPException(404,"Unknown case ID")
    return {"case_id":c.id,"legs":c.legs,"synthetic":True}
@router.get("/api/cases/{case_id}/alternatives")
def alternatives(case_id:str,db:Session=Depends(get_db)):
    """Compatibility route: return AirLabs records; never training-flight suggestions."""
    return live_alternatives(case_id,None,db)["records"]
@router.get("/api/cases/{case_id}/policy")
def policy(case_id:str,db:Session=Depends(get_db)):
    c=db.get(Case,case_id)
    if not c: raise HTTPException(404,"Unknown case ID")
    # Pre-search case policy: eligibility is assessed only after AirLabs rows are
    # fetched by the recovery graph. Training fixtures never influence this result.
    p=evaluate(c.legs,c.evidence_complete,c.review_required,1)
    return {"decision":p.decision,"reason_codes":p.reason_codes,"connections":p.connections,"human_review_required":p.human_review_required,"minimum_connection_minutes":60}
@router.post("/api/cases/{case_id}/analyze")
@router.post("/api/cases/{case_id}/recovery")
def analyze(case_id:str,db:Session=Depends(get_db)):
    # Both public recovery entry points use AirLabs candidates. Training
    # alternatives remain available only to isolated demo/unit workflows.
    return live_recovery(case_id,None,db)
@router.get("/api/runs/{run_id}")
def get_run(run_id:str,db:Session=Depends(get_db)):
    r=db.get(Run,run_id)
    if not r: raise HTTPException(404,"Unknown run ID")
    return {"run_id":r.id,"case_id":r.case_id,"status":r.status,"report":r.report,"created_at":str(r.created_at)}
@router.get("/api/runs/{run_id}/trace")
def get_trace(run_id:str,db:Session=Depends(get_db)):
    r=db.get(Run,run_id)
    if not r: raise HTTPException(404,"Unknown run ID")
    return {"run_id":r.id,"steps":r.trace}
class ReviewBody(BaseModel): operator_id:str="local-operator"; note:str=""
def decide(recommendation_id:str,decision:str,body:ReviewBody,db:Session):
    rec=db.get(Recommendation,recommendation_id)
    if not rec: raise HTTPException(404,"Unknown recommendation")
    run=db.get(Run,rec.run_id)
    if not run or not run.report.get("human_review_required"): raise HTTPException(409,"This recommendation does not permit human approval")
    if run.report.get("policy_decision")=="proceed" and "missing_required_evidence" in run.report.get("reason_codes",[]): raise HTTPException(409,"Required evidence is missing")
    if rec.decision:
        if rec.decision==decision:return {"recommendation_id":rec.id,"status":rec.status,"decision":decision,"reviewed_at":str(rec.reviewed_at)}
        raise HTTPException(409,"Recommendation already has a contradictory decision")
    rec.decision=decision;rec.status=decision;rec.reviewed_at=datetime.now(timezone.utc);db.commit()
    return {"recommendation_id":rec.id,"status":rec.status,"decision":decision,"reviewed_at":str(rec.reviewed_at)}
@router.post("/api/reviews/{recommendation_id}/approve")
def approve(recommendation_id:str,body:ReviewBody,db:Session=Depends(get_db)): return decide(recommendation_id,"approved",body,db)
@router.post("/api/reviews/{recommendation_id}/reject")
def reject(recommendation_id:str,body:ReviewBody,db:Session=Depends(get_db)): return decide(recommendation_id,"rejected",body,db)
