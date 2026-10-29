from app.policy.engine import assess_connections
URGENT_TYPES={"Flight cancellation","Missed connection","Diversion recovery","Regional service cancellation","Runway closure"}
def classify_attention(case)->dict:
    connections,_=assess_connections(case.legs or [])
    failed=next((x for x in connections if not x["feasible"]),None)
    if failed:
        minutes=failed["minutes"]
        summary=f"Only {minutes if minutes is not None else 'an unknown number of'} minutes to connect; 60 minutes are required."
        return {"priority":"urgent","priority_label":"Immediate attention","action_by":"Now · before the next flight","attention_summary":summary,"human_review_required":True,"priority_rank":0}
    if case.disruption in URGENT_TYPES:
        return {"priority":"urgent","priority_label":"Immediate attention","action_by":"Now · confirm next steps","attention_summary":f"{case.disruption} needs an operator to check the passenger’s next step.","human_review_required":True,"priority_rank":0}
    if not case.evidence_complete:
        return {"priority":"review","priority_label":"Evidence check","action_by":"Before recovery advice","attention_summary":"Required disruption details need confirmation before options are reviewed.","human_review_required":True,"priority_rank":1}
    if case.review_required:
        return {"priority":"review","priority_label":"Human review","action_by":"Within 30 minutes","attention_summary":"An operator must confirm this itinerary before a customer update.","human_review_required":True,"priority_rank":1}
    return {"priority":"monitor","priority_label":"Monitor","action_by":"Recheck in 30 minutes","attention_summary":"No immediate connection issue is flagged; keep the case under review.","human_review_required":False,"priority_rank":2}
