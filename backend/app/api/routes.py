from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uuid import uuid4
from datetime import datetime, timezone
from app.db import get_db,Base,engine
from app.seed import seed
from app.models import Case,Alternative,Run,Recommendation
from app.graph.workflow import run_workflow
from app.policy.engine import evaluate, assess_alternatives
from app.agents.llm import ConfigurationError,ProviderError
from app.services.labels import airline_for_flight
from app.services.attention import classify_attention
router=APIRouter()
@router.get("/health")
def health(): return {"status":"ok","data_mode":"synthetic_demo","model":"gemini-3.5-flash-lite"}
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
    if not db.get(Case,case_id): raise HTTPException(404,"Unknown case ID")
    candidates=[{"flight":a.flight,"airline":airline_for_flight(a.flight),"origin":a.origin,"destination":a.destination,"departure":a.departure,"arrival":a.arrival,"eligible":a.eligible,"reason":a.reason} for a in db.query(Alternative).filter_by(case_id=case_id).all()]
    return assess_alternatives({"origin":db.get(Case,case_id).origin,"destination":db.get(Case,case_id).destination},candidates)
@router.get("/api/cases/{case_id}/policy")
def policy(case_id:str,db:Session=Depends(get_db)):
    c=db.get(Case,case_id)
    if not c: raise HTTPException(404,"Unknown case ID")
    alts=db.query(Alternative).filter_by(case_id=case_id).all()
    assessments=assess_alternatives({"origin":c.origin,"destination":c.destination},[{"flight":a.flight,"origin":a.origin,"destination":a.destination,"departure":a.departure,"arrival":a.arrival,"eligible":a.eligible,"reason":a.reason} for a in alts])
    p=evaluate(c.legs,c.evidence_complete,c.review_required,sum(a["eligible"] for a in assessments))
    return {"decision":p.decision,"reason_codes":p.reason_codes,"connections":p.connections,"human_review_required":p.human_review_required,"minimum_connection_minutes":60}
@router.post("/api/cases/{case_id}/analyze")
@router.post("/api/cases/{case_id}/recovery")
def analyze(case_id:str,db:Session=Depends(get_db)):
    if not db.get(Case,case_id): raise HTTPException(404,"Unknown case ID")
    try:
        rid,report,trace,failure=run_workflow(db,case_id)
        if failure:
            db.add(Run(id=rid,case_id=case_id,status="failed",report={"run_id":rid,"case_id":case_id,"workflow_status":"failed","error":failure},trace=trace));db.commit()
            raise HTTPException(503,detail={"run_id":rid,**failure})
        db.add(Run(id=rid,case_id=case_id,status=report["workflow_status"],report=report,trace=trace)); db.commit()
        if report["human_review_required"]:
            db.add(Recommendation(id=report["recommendation_id"],run_id=rid)); db.commit()
        return report
    except HTTPException:
        raise
    except (ConfigurationError,ProviderError) as exc:
        rid=str(uuid4()); msg=str(exc)
        trace=[{"step":1,"agent":"Orchestrator","status":"failed","error_category":"configuration" if isinstance(exc,ConfigurationError) else "provider","error_message":msg}]
        db.add(Run(id=rid,case_id=case_id,status="failed",report={"run_id":rid,"case_id":case_id,"workflow_status":"failed","error":{"category":trace[0]["error_category"],"message":msg}},trace=trace));db.commit()
        raise HTTPException(503,detail={"run_id":rid,"category":trace[0]["error_category"],"message":msg})
    except Exception as exc:
        rid=str(uuid4());msg="Workflow tool or execution failure"
        trace=[{"step":1,"agent":"Orchestrator","status":"failed","error_category":"tool_execution","error_message":type(exc).__name__}]
        db.add(Run(id=rid,case_id=case_id,status="failed",report={"run_id":rid,"case_id":case_id,"workflow_status":"failed","error":{"category":"tool_execution","message":msg}},trace=trace));db.commit()
        raise HTTPException(500,detail={"run_id":rid,"category":"tool_execution","message":msg})
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
