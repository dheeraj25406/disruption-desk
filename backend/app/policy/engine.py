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

def assess_provider_alternative(case:dict,alternative:dict)->dict:
    """Evaluate schedule fit only; this is never a seat, fare, or booking check."""
    from datetime import datetime
    reasons=[]
    if alternative.get("source") not in {"airlabs", "airlabs_route_pattern"}: reasons.append("unverified_provider_source")
    if alternative.get("origin")!=case.get("origin") or alternative.get("destination")!=case.get("destination"):
        reasons.append("alternative_route_mismatch")
    try:
        departure=datetime.fromisoformat(alternative["departure"].replace("Z","+00:00"))
        arrival=datetime.fromisoformat(alternative["arrival"].replace("Z","+00:00"))
        disrupted_departure=datetime.fromisoformat(case["legs"][0]["departure"].replace("Z","+00:00"))
        # Seeded domestic demo itineraries may use local naive timestamps while live
        # provider rows carry offsets. Compare wall-clock values only for mixed shapes.
        if (departure.tzinfo is None) != (disrupted_departure.tzinfo is None):
            departure=departure.replace(tzinfo=None); arrival=arrival.replace(tzinfo=None)
            disrupted_departure=disrupted_departure.replace(tzinfo=None)
        if arrival<=departure: reasons.append("invalid_candidate_schedule")
        if departure<disrupted_departure: reasons.append("departs_before_disrupted_itinerary")
    except (KeyError,IndexError,TypeError,ValueError,AttributeError):
        reasons.append("invalid_candidate_schedule")
    if (alternative.get("flight_status") or "").casefold()=="cancelled":
        reasons.append("provider_reports_cancelled")
    eligible=not reasons
    basis=alternative.get("schedule_basis")
    explanation=(("AirLabs publishes this as a recurring route pattern for the requested weekday; live operation, seat availability, and fare are not provided." if basis=="published_route_pattern" else "Provider schedule matches the route and disruption date; seat availability and fare are not provided.") if eligible
                 else "Schedule does not meet the route or timing checks: "+", ".join(reasons))
    return {**alternative,"eligible":eligible,"reason":explanation,"eligibility_reason_codes":reasons,"availability_confirmed":False}

def rank_provider_alternatives(alternatives:list[dict],limit:int=3)->list[dict]:
    """Return a compact shortlist: earliest eligible departure, then earliest arrival.

    Duplicate schedule slots are collapsed so codeshare rows do not consume the
    shortlist. This is a schedule-fit ranking only; it cannot assert inventory.
    """
    eligible=[row for row in alternatives if row.get("eligible")]
    eligible.sort(key=lambda row:(row.get("departure",""),row.get("arrival",""),row.get("flight","")))
    chosen=[]; slots=set()
    for row in eligible:
        slot=(str(row.get("departure",""))[:16],str(row.get("arrival",""))[:16])
        if slot in slots: continue
        slots.add(slot); chosen.append(row)
        if len(chosen)==limit: break
    return [{**row,"shortlist_rank":idx+1,"is_best_match":idx==0} for idx,row in enumerate(chosen)]

def evaluate(legs:list[dict],evidence_complete:bool,review_required:bool,eligible_count:int)->PolicyResult:
    checks,reasons=assess_connections(legs)
    if not evidence_complete: reasons.append("missing_required_evidence")
    if review_required: reasons.append("itinerary_connection_requires_review")
    if eligible_count==0: reasons.append("no_eligible_alternatives")
    unique=list(dict.fromkeys(reasons))
    blocking=[reason for reason in unique if reason!="itinerary_connection_requires_review"]
    return PolicyResult("escalate" if blocking else "proceed",unique,checks,bool(review_required or blocking))
