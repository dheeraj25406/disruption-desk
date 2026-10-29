AIRLINES={"AI":"Air India","6E":"IndiGo","IX":"Air India Express","QP":"Akasa Air","SG":"SpiceJet"}
def airline_for_flight(flight:str)->str:
    parts=flight.replace("DEMO-","").replace("-"," ").split()
    code=parts[0] if parts else ""
    return AIRLINES.get(code,"Indian airline")
def display_flight(flight:str)->str:
    if flight.startswith("DEMO-"):
        parts=flight.split("-")
        if len(parts)>=3 and parts[1] in AIRLINES: return f"{parts[1]} {parts[2]}"
    return flight
