from typing import TypedDict, Any
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from sqlalchemy.orm import Session
from app.tools.registry import build_tools
from app.policy.engine import evaluate, assess_alternatives
from app.schemas.reports import Report
from app.agents.llm import explanation, ConfigurationError, ProviderError

class WorkflowState(TypedDict, total=False):
    case_id:str; run_id:str; case:dict; alternatives:list[dict]; policy:dict; trace:list[dict]; report:dict; error:dict; evidence_issues:list[str]

def build_graph(db:Session, explain_fn=explanation):
    tools=build_tools(db)
    def data_agent(s:WorkflowState):
        result=tools["get_disruption_case"].invoke({"case_id":s["case_id"]})
        itinerary=tools["get_itinerary"].invoke({"case_id":s["case_id"]})
        flight=tools["get_flight_details"].invoke({"case_id":s["case_id"]})
        connection=tools["check_connection_feasibility"].invoke({"case_id":s["case_id"]})
        issues=[]
        if itinerary["legs"]!=result["legs"]: issues.append("case_itinerary_record_mismatch")
        if flight["flight"]!=result["flight"] or flight["origin"]!=result["origin"] or flight["destination"]!=result["destination"]: issues.append("affected_flight_record_mismatch")
        traces=[{"step":1,"agent":"Data Agent","tool":"get_disruption_case","status":"completed","evidence_refs":[s["case_id"]],"result_summary":"Loaded case and disruption evidence"},{"step":2,"agent":"Data Agent","tool":"get_itinerary","status":"completed","evidence_refs":[s["case_id"]],"result_summary":f"Loaded {len(itinerary['legs'])} itinerary legs"},{"step":3,"agent":"Data Agent","tool":"get_flight_details","status":"completed","evidence_refs":[s["case_id"]],"result_summary":"Loaded affected flight and route"},{"step":4,"agent":"Data Agent","tool":"check_connection_feasibility","status":"completed","evidence_refs":[s["case_id"]],"result_summary":f"Checked {len(connection['assessments'])} connections against {connection['minimum_minutes']} minutes"}]
        result["legs"]=itinerary["legs"]
        if issues: result["evidence_complete"]=False
        return {"case":result,"evidence_issues":issues,"trace":s.get("trace",[])+traces}
    def validation(s):
        c=s["case"]
        missing=not c["evidence_complete"]
        return {"trace":s["trace"]+[{"step":5,"agent":"Evidence Validator","status":"completed","result_summary":("Required evidence checked" if not missing else "Missing required evidence; recovery search skipped") + ("; record contradictions found" if s.get("evidence_issues") else "")}]}
    def policy(s):
        c=s["case"]
        rules=tools["get_policy_rules"].invoke({})
        alts=[tools["evaluate_alternative_eligibility"].invoke({"case_id":s["case_id"],**candidate}) for candidate in s.get("alternatives",[])]
        if rules["minimum_connection_minutes"]!=60: raise ValueError("unsupported_policy_configuration")
        p=evaluate(c["legs"],c["evidence_complete"],c["review_required"],sum(a["eligible"] for a in alts))
        trace=s["trace"]+[{"step":7,"agent":"Policy Engine","tool":"get_policy_rules","status":"completed","result_summary":"Loaded deterministic thresholds and review constraints"}]
        if alts: trace.append({"step":8,"agent":"Policy Engine","tool":"evaluate_alternative_eligibility","status":"completed","result_summary":f"Applied deterministic eligibility checks to {len(alts)} candidates"})
        trace.append({"step":9,"agent":"Policy Engine","status":"completed","result_summary":"Applied connection, evidence, candidate, and human-review rules"})
        return {"alternatives":alts,"policy":p.__dict__,"trace":trace}
    def recovery(s):
        alts=tools["search_synthetic_alternatives"].invoke({"case_id":s["case_id"]})
        return {"alternatives":alts,"trace":s["trace"]+[{"step":6,"agent":"Recovery Agent","tool":"search_synthetic_alternatives","status":"completed","evidence_refs":[a["flight"] for a in alts] or [s["case_id"]],"result_summary":f"Compared {len(alts)} candidate flight records"}]}
    def synthesize(s):
        c=s["case"]; p=s["policy"]; eligible=[a for a in s.get("alternatives",[]) if a["eligible"]]
        try:
            text=explain_fn(c,p["decision"],p["reason_codes"],eligible)
        except ConfigurationError as exc:
            return {"error":{"category":"configuration","message":str(exc)},"trace":s["trace"]+[{"step":10,"agent":"Orchestrator","status":"failed","error_category":"configuration","error_message":str(exc)}]}
        except ProviderError as exc:
            return {"error":{"category":"provider","message":str(exc)},"trace":s["trace"]+[{"step":10,"agent":"Orchestrator","status":"failed","error_category":"provider","error_message":str(exc)}]}
        except Exception as exc:
            return {"error":{"category":"provider","message":"AI explanation failed"},"trace":s["trace"]+[{"step":10,"agent":"Orchestrator","status":"failed","error_category":"provider","error_message":type(exc).__name__}]}
        status="escalated" if p["decision"]=="escalate" else ("awaiting_human_review" if p["human_review_required"] else "completed")
        report=Report(run_id=s["run_id"],case_id=c["case_id"],recommendation_id=str(uuid4()) if p["human_review_required"] else None,workflow_status=status,affected_flight=c["flight"],origin=c["origin"],destination=c["destination"],itinerary_summary="; ".join(f"{x['origin']} → {x['destination']} {x['departure']}–{x['arrival']}" for x in c["legs"]),disruption_summary=c["detail"],policy_decision=p["decision"],reason_codes=p["reason_codes"],connection_assessments=p["connections"],candidate_alternatives=s.get("alternatives",[]),recommended_action="Escalate to an operator for review" if status=="escalated" else (f"Review simulated candidate {eligible[0]['flight']}" if eligible else "No eligible synthetic alternative; operator review required"),explanation=text,evidence=[{"source_id":c["case_id"],"summary":f"Synthetic case, disruption, and {len(c['legs'])} itinerary leg(s)"}],human_review_required=p["human_review_required"],human_review_status="pending" if p["human_review_required"] else "not_required",agent_trace_summary=s["trace"]+[ {"step":10,"agent":"Orchestrator","status":"completed","result_summary":"Validated structured report; policy decision preserved"}],limitations=["Training records are for demonstration; airline inventory and operational status are not live.","Recommendation preparation does not book, cancel, refund, or rebook."])
        return {"report":report.model_dump(mode="json"),"trace":s["trace"]+[{"step":10,"agent":"Orchestrator","status":"completed","result_summary":"Validated structured report; policy decision preserved"}]}
    g=StateGraph(WorkflowState)
    g.add_node("data_agent",data_agent);g.add_node("validate_evidence",validation);g.add_node("policy_engine",policy);g.add_node("recovery_agent",recovery);g.add_node("synthesize",synthesize)
    g.add_edge(START,"data_agent");g.add_edge("data_agent","validate_evidence")
    g.add_conditional_edges("validate_evidence",lambda s:"recovery_agent" if s["case"]["evidence_complete"] else "policy_engine",{"recovery_agent":"recovery_agent","policy_engine":"policy_engine"})
    g.add_edge("recovery_agent","policy_engine");g.add_edge("policy_engine","synthesize");g.add_edge("synthesize",END)
    return g.compile()

def run_workflow(db:Session,case_id:str,explain_fn=explanation):
    rid=str(uuid4())
    result=build_graph(db,explain_fn).invoke({"case_id":case_id,"run_id":rid,"trace":[]},config={"recursion_limit":12})
    return rid,result.get("report"),result["trace"],result.get("error")
