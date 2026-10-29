from dataclasses import dataclass
from datetime import datetime
MIN_CONNECTION_MINUTES=60

@dataclass
class PolicyResult:
    decision:str
    reason_codes:list[str]
    connections:list[dict]
    human_review_required:bool

def assess_connections(legs:list[dict])->tuple[list[dict],list[str]]:
    checks=[]; reasons=[]
    for idx,(left,right) in enumerate(zip(legs,legs[1:]),1):
        try:
            arrival=datetime.fromisoformat(left["arrival"])
            departure=datetime.fromisoformat(right["departure"])
            minutes=int((departure-arrival).total_seconds()/60)
        except (KeyError,TypeError,ValueError):
            minutes=None
        feasible=minutes is not None and minutes>=MIN_CONNECTION_MINUTES
        checks.append({"from_leg":idx,"minutes":minutes,"minimum_minutes":MIN_CONNECTION_MINUTES,"feasible":feasible})
        if not feasible: reasons.append("below_minimum_connection_buffer")
    return checks,reasons

def assess_alternative(case:dict,alternative:dict)->dict:
    reasons=[]
    if not alternative.get("eligible",False): reasons.append("candidate_not_seeded_eligible")
    if alternative.get("origin")!=case.get("origin") or alternative.get("destination")!=case.get("destination"):
        reasons.append("alternative_route_mismatch")
    try:
        departure=datetime.fromisoformat(alternative["departure"])
        arrival=datetime.fromisoformat(alternative["arrival"])
        if arrival<=departure: reasons.append("invalid_candidate_schedule")
    except (KeyError,TypeError,ValueError): reasons.append("invalid_candidate_schedule")
    return {**alternative,"eligible":not reasons,"reason":("Eligible: meets seeded, route, and schedule rules" if not reasons else "Rejected: "+", ".join(reasons)),"eligibility_reason_codes":reasons}

def assess_alternatives(case:dict,alternatives:list[dict])->list[dict]:
    return [assess_alternative(case,a) for a in alternatives]

def evaluate(legs:list[dict],evidence_complete:bool,review_required:bool,eligible_count:int)->PolicyResult:
    checks,reasons=assess_connections(legs)
    if not evidence_complete: reasons.append("missing_required_evidence")
    if review_required: reasons.append("itinerary_connection_requires_review")
    if eligible_count==0: reasons.append("no_eligible_alternatives")
    return PolicyResult("escalate" if reasons else "proceed",list(dict.fromkeys(reasons)),checks,bool(reasons))
