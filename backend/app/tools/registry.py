from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.models import Case, Alternative
from app.policy.engine import assess_connections, assess_alternative, MIN_CONNECTION_MINUTES
from app.services.labels import airline_for_flight

class CaseInput(BaseModel): case_id:str=Field(min_length=1,description="Synthetic case identifier")
class SearchInput(BaseModel): case_id:str=Field(min_length=1,description="Synthetic case identifier")
class EligibilityInput(BaseModel):
    case_id:str=Field(min_length=1)
    flight:str=Field(min_length=1)
    airline:str=""
    origin:str=Field(min_length=3,max_length=3)
    destination:str=Field(min_length=3,max_length=3)
    departure:str
    arrival:str
    eligible:bool
    reason:str=""

def _case_record(row:Case)->dict:
    return {"case_id":row.id,"passenger_label":row.passenger_label,"flight":row.flight,"airline":row.airline,"origin":row.origin,"destination":row.destination,"disruption":row.disruption,"detail":row.detail,"evidence_complete":row.evidence_complete,"review_required":row.review_required,"legs":row.legs}

def build_tools(db:Session):
    @tool(args_schema=CaseInput)
    def get_disruption_case(case_id:str)->dict:
        """Retrieve the synthetic disruption case, disruption facts, and evidence flags."""
        row=db.get(Case,case_id)
        if row is None: raise ValueError(f"unknown_case:{case_id}")
        return _case_record(row)
    @tool(args_schema=CaseInput)
    def get_itinerary(case_id:str)->dict:
        """Retrieve all stored itinerary legs for a synthetic case."""
        row=db.get(Case,case_id)
        if row is None: raise ValueError(f"unknown_case:{case_id}")
        return {"case_id":row.id,"legs":row.legs,"source":"synthetic_demo_database"}
    @tool(args_schema=CaseInput)
    def get_flight_details(case_id:str)->dict:
        """Retrieve affected flight identifier and synthetic airline label."""
        row=db.get(Case,case_id)
        if row is None: raise ValueError(f"unknown_case:{case_id}")
        return {"flight":row.flight,"airline":row.airline,"origin":row.origin,"destination":row.destination,"source":"synthetic_demo_database"}
    @tool(args_schema=CaseInput)
    def check_connection_feasibility(case_id:str)->dict:
        """Calculate stored itinerary connection buffers against the 60-minute policy minimum."""
        row=db.get(Case,case_id)
        if row is None: raise ValueError(f"unknown_case:{case_id}")
        checks,reasons=assess_connections(row.legs)
        return {"minimum_minutes":MIN_CONNECTION_MINUTES,"assessments":checks,"reason_codes":reasons}
    @tool(args_schema=SearchInput)
    def search_synthetic_alternatives(case_id:str)->list[dict]:
        """Search the synthetic alternative-flight records for a case."""
        if db.get(Case,case_id) is None: raise ValueError(f"unknown_case:{case_id}")
        return [dict(flight=x.flight,airline=airline_for_flight(x.flight),origin=x.origin,destination=x.destination,departure=x.departure,arrival=x.arrival,eligible=x.eligible,reason=x.reason) for x in db.query(Alternative).filter_by(case_id=case_id).all()]
    @tool(args_schema=EligibilityInput)
    def evaluate_alternative_eligibility(case_id:str,flight:str,origin:str,destination:str,departure:str,arrival:str,eligible:bool,airline:str="",reason:str="")->dict:
        """Apply deterministic route, schedule, and seeded-eligibility policy to one synthetic candidate."""
        row=db.get(Case,case_id)
        if row is None: raise ValueError(f"unknown_case:{case_id}")
        return assess_alternative(_case_record(row),{"flight":flight,"airline":airline or airline_for_flight(flight),"origin":origin,"destination":destination,"departure":departure,"arrival":arrival,"eligible":eligible,"reason":reason})
    @tool
    def get_policy_rules()->dict:
        """Return deterministic policy thresholds and approval constraints. Takes no arguments."""
        return {"minimum_connection_minutes":MIN_CONNECTION_MINUTES,"policy_is_deterministic":True,"human_review_is_separate":True,"booking_actions_enabled":False}
    return {t.name:t for t in (get_disruption_case,get_itinerary,get_flight_details,check_connection_feasibility,search_synthetic_alternatives,evaluate_alternative_eligibility,get_policy_rules)}
