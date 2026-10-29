from pydantic import BaseModel, Field
from typing import Literal
class Evidence(BaseModel): source_id: str; summary: str; source: str = "training_case_database"
class Candidate(BaseModel):
    flight: str; airline: str | None = None; origin: str; destination: str
    departure: str; arrival: str; eligible: bool; reason: str
    source: Literal["training_fixture", "airlabs", "airlabs_route_pattern"] = "training_fixture"
    schedule_basis: str | None = None
    departure_local_time: str | None = None
    arrival_local_time: str | None = None
    operating_days: list[str] = Field(default_factory=list)
    shortlist_rank: int | None = None
    is_best_match: bool = False
    flight_status: str | None = None
    provider_flight_id: str | None = None
    availability_confirmed: bool = False
class Report(BaseModel):
    run_id: str; case_id: str; recommendation_id: str | None = None; workflow_status: Literal["completed","escalated","failed","incomplete","awaiting_human_review"]
    affected_flight: str; origin: str; destination: str; itinerary_summary: str; disruption_summary: str
    policy_decision: Literal["proceed","escalate"]; reason_codes: list[str]; connection_assessments: list[dict]
    candidate_alternatives: list[Candidate]; best_candidate_flight: str | None = None; recommended_action: str; explanation: str; evidence: list[Evidence]
    human_review_required: bool; human_review_status: str; agent_trace_summary: list[dict]; limitations: list[str]
