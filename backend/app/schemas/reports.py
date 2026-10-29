from pydantic import BaseModel, Field
from typing import Literal
class Evidence(BaseModel): source_id: str; summary: str; source: str = "synthetic_demo_database"
class Candidate(BaseModel): flight: str; airline: str = ""; origin: str; destination: str; departure: str; arrival: str; eligible: bool; reason: str
class Report(BaseModel):
    run_id: str; case_id: str; recommendation_id: str | None = None; workflow_status: Literal["completed","escalated","failed","incomplete","awaiting_human_review"]
    affected_flight: str; origin: str; destination: str; itinerary_summary: str; disruption_summary: str
    policy_decision: Literal["proceed","escalate"]; reason_codes: list[str]; connection_assessments: list[dict]
    candidate_alternatives: list[Candidate]; recommended_action: str; explanation: str; evidence: list[Evidence]
    human_review_required: bool; human_review_status: str; agent_trace_summary: list[dict]; limitations: list[str]
