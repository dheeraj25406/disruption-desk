from app.models import Case, Alternative
from app.db import Base,engine,SessionLocal
from datetime import datetime, timedelta, timezone
import re
from app.services.labels import AIRLINES

def dt(day,hour,minute=0):
    base=datetime(2026,10,30,tzinfo=timezone(timedelta(hours=5,minutes=30)))
    return (base+timedelta(days=day-30,hours=hour,minutes=minute)).isoformat(timespec="seconds")

def generated_legs(idx,origin,destination,airports):
    mid=airports[(idx+13)%len(airports)]
    count=1+(idx%3)
    departure_minutes=(5+(idx%12))*60
    legs=[]
    for leg_idx in range(count):
        a=origin if leg_idx==0 else (mid if leg_idx==1 else airports[(idx+17)%len(airports)])
        b=destination if leg_idx==count-1 else (mid if leg_idx==0 else airports[(idx+17)%len(airports)])
        depart=departure_minutes
        duration=85+(idx*11+leg_idx*19)%126
        arrive=depart+duration
        legs.append({"origin":a,"destination":b,"departure":dt(30,depart//60,depart%60),"arrival":dt(30,arrive//60,arrive%60)})
        departure_minutes=arrive+(25 if idx%9==0 and leg_idx==0 else 75)
    return legs

def seed():
    Base.metadata.create_all(engine); db=SessionLocal()
    try:
        rows=[
        Case(id="INDEMO0025",passenger_label="Synthetic passenger 25",flight="DEMO-AI-2125",airline="Air India",origin="BOM",destination="GOI",disruption="Schedule disruption",detail="Schedule disruption affects a two-leg itinerary.",evidence_complete=True,review_required=True,legs=[{"origin":"BOM","destination":"COK","departure":dt(30,9),"arrival":dt(30,11)},{"origin":"COK","destination":"GOI","departure":dt(30,11,30),"arrival":dt(30,13,30)}]),
        Case(id="INDEMO0001",passenger_label="Synthetic passenger 01",flight="DEMO-FY-1001",airline="Flyo Demo Air",origin="DEL",destination="BLR",disruption="Flight cancellation",detail="First leg cancelled; a same-day simulated direct candidate exists.",evidence_complete=True,review_required=False,legs=[{"origin":"DEL","destination":"BLR","departure":dt(30,8),"arrival":dt(30,10)}]),
        Case(id="INDEMO0002",passenger_label="Synthetic passenger 02",flight="DEMO-FY-1002",airline="Flyo Demo Air",origin="BOM",destination="MAA",disruption="Missed connection",detail="Connection buffer is below the configured minimum.",evidence_complete=True,review_required=False,legs=[{"origin":"BOM","destination":"HYD","departure":dt(30,7),"arrival":dt(30,9)},{"origin":"HYD","destination":"MAA","departure":dt(30,9,30),"arrival":dt(30,11)}]),
        Case(id="INDEMO0003",passenger_label="Synthetic passenger 03",flight="DEMO-FY-1003",airline="Flyo Demo Air",origin="CCU",destination="GAU",disruption="Weather delay",detail="No eligible synthetic candidate is seeded.",evidence_complete=True,review_required=False,legs=[{"origin":"CCU","destination":"GAU","departure":dt(30,12),"arrival":dt(30,13)}]),
        Case(id="INDEMO0004",passenger_label="Synthetic passenger 04",flight="DEMO-FY-1004",airline="Flyo Demo Air",origin="PNQ",destination="GOI",disruption="Data discrepancy",detail="Required disruption evidence is incomplete.",evidence_complete=False,review_required=True,legs=[{"origin":"PNQ","destination":"GOI","departure":dt(30,14),"arrival":dt(30,15)}]),
        Case(id="INDEMO0005",passenger_label="Synthetic passenger 05",flight="DEMO-FY-1005",airline="Flyo Demo Air",origin="DEL",destination="COK",disruption="Aircraft change",detail="Multi-leg itinerary with several synthetic candidate records.",evidence_complete=True,review_required=False,legs=[{"origin":"DEL","destination":"BOM","departure":dt(30,6),"arrival":dt(30,8)},{"origin":"BOM","destination":"COK","departure":dt(30,9,15),"arrival":dt(30,11)}]),
        Case(id="INDEMO0006",passenger_label="Synthetic passenger 06",flight="DEMO-FY-1006",airline="Flyo Demo Air",origin="BLR",destination="DEL",disruption="Schedule change",detail="Candidates exist, but manual itinerary review is configured.",evidence_complete=True,review_required=True,legs=[{"origin":"BLR","destination":"DEL","departure":dt(30,16),"arrival":dt(30,19)}])]
        existing_ids={x[0] for x in db.query(Case.id).all()}
        rows=[row for row in rows if row.id not in existing_ids]
        db.add_all(rows); db.flush()
        defs=[("INDEMO0001","AI 2001","DEL","BLR",8,30,10,20,True),("INDEMO0003","QP 2003","CCU","GAU",15,0,16,0,False),("INDEMO0005","SG 3001","DEL","COK",12,0,16,0,True),("INDEMO0005","SG 3002","DEL","COK",13,0,17,0,True),("INDEMO0005","SG 3003","DEL","COK",14,0,18,0,False),("INDEMO0006","AI 6001","BLR","DEL",20,0,23,0,True)]
        seen_alts=set()
        for existing in db.query(Alternative).order_by(Alternative.id).all():
            key=(existing.case_id,existing.flight)
            if key in seen_alts: db.delete(existing)
            else: seen_alts.add(key)
        db.flush()
        existing_alts={(x.case_id,x.flight) for x in db.query(Alternative.case_id,Alternative.flight).all()}
        for cid,flight,o,d,dh,dm,ah,am,eligible in defs:
            if (cid,flight) not in existing_alts:
                db.add(Alternative(case_id=cid,flight=flight,origin=o,destination=d,departure=dt(30,dh,dm),arrival=dt(30,ah,am),eligible=eligible,reason="Meets route and schedule requirements" if eligible else "Does not meet route, schedule or eligibility requirements"))
        current_count=db.query(Case).count()+len(rows)
        extra_types=[
          "Gate change", "Aircraft substitution", "Crew legality delay", "Late inbound aircraft", "Air traffic flow restriction", "Airport curfew risk", "Diversion recovery", "Ground stop", "Deicing delay", "Technical inspection hold", "Cabin maintenance delay", "Baggage loading delay", "Passenger reaccommodation", "Oversale protection review", "Operating carrier change", "Codeshare schedule mismatch", "Terminal transfer constraint", "Security queue delay", "Medical offload delay", "Fuel uplift delay", "Ramp congestion", "Runway closure", "Airport slot restriction", "Navigation equipment outage", "Weather reroute", "Thunderstorm ground delay", "Low visibility operation", "Crosswind restriction", "Bird strike inspection", "Hydraulic maintenance hold", "Cabin pressure warning", "Passenger connection protection", "Involuntary overnight risk", "Long delay threshold review", "Flight number retime", "Departure time advance", "Arrival station change", "Aircraft rotation disruption", "Regional service cancellation", "International document hold", "Transit visa evidence gap", "Mobility assistance transfer", "Unaccompanied minor transfer"]
        airports=["DEL","BOM","BLR","MAA","HYD","CCU","COK","GOI","AMD","PNQ","JAI","LKO","GAU","IXC","BBI","TRV","ATQ","NAG","VNS","IDR","PAT","RPR","SXR","UDR","BDQ"]
        extra_alts=[]
        for i in range(max(0,50-db.query(Case).count())):
            idx=i
            case_id=f"INDEMO{100+i:04d}"
            if db.get(Case,case_id): continue
            origin=airports[idx%len(airports)]; destination=airports[(idx+7+(idx//len(airports)))%len(airports)]
            if destination==origin: destination=airports[(idx+1)%len(airports)]
            legs=generated_legs(idx,origin,destination,airports)
            passenger_num=100+i
            rows_extra=Case(id=case_id,passenger_label=f"Synthetic passenger {passenger_num}",flight=f"{['AI','6E','IX','QP','SG'][idx%5]} {5000+idx}",airline=["Air India","IndiGo","Air India Express","Akasa Air","SpiceJet"][idx%5],origin=origin,destination=destination,disruption=extra_types[idx],detail=f"{extra_types[idx]} affecting the passenger itinerary. Review the flight records, disruption details, candidate options, and connection requirements.",evidence_complete=(idx%11!=0),review_required=(idx%5==0),legs=legs)
            db.add(rows_extra); db.flush()
            candidate_count=idx%4
            for j in range(candidate_count):
                eligible=idx%4 not in (1,) and j==0
                dep_hour=min(22,8+(idx%10)+j)
                arr_hour=min(23,dep_hour+2+(idx%3))
                extra_alts.append(Alternative(case_id=case_id,flight=f"{['AI','6E','IX','QP','SG'][(idx+j+1)%5]} {7000+idx*3+j:04d}",origin=origin,destination=destination,departure=dt(30,dep_hour,0),arrival=dt(30,arr_hour,0),eligible=eligible,reason="Meets listed route and schedule criteria" if eligible else "Does not meet listed route and schedule criteria"))
        if extra_alts: db.add_all(extra_alts)
        db.flush()
        names=["Aarav Mehta","Ananya Iyer","Rohan Malhotra","Diya Nair","Arjun Rao","Meera Kapoor","Vihaan Patel","Aditi Menon","Ishaan Shah","Kavya Reddy","Reyansh Bhatia","Saanvi Kulkarni","Aditya Chawla","Ira Deshmukh","Kabir Sethi","Myra Krishnan","Advait Joshi","Tara Mukherjee","Dhruv Anand","Pari Srinivasan","Vivaan Khanna","Nisha Pillai","Kiaan Verma","Riya Banerjee","Neil Fernandes","Suhana Das","Yash Thakur","Anika Bose","Om Prakash","Sakshi Jain","Arnav Ghosh","Mira Subramanian","Kunal Arora","Navya Shetty","Dev Malhotra","Ishita Roy","Ayaan Kapoor","Pooja Nambiar","Samar Gill","Tanvi Rao","Rahul Bansal","Lavanya Menon","Manav Sood","Jhanvi Desai","Parth Trivedi","Shreya Sinha","Nikhil Dutta","Anvi Narang","Ritvik Kulkarni","Sia Chatterjee"]
        carrier_codes={v:k for k,v in AIRLINES.items()}
        core_flights={"INDEMO0001":"AI","INDEMO0002":"6E","INDEMO0003":"QP","INDEMO0004":"IX","INDEMO0005":"SG","INDEMO0006":"AI"}
        for pos,row in enumerate(db.query(Case).order_by(Case.id).all()):
            row.passenger_label=names[pos%len(names)]
            row.detail=row.detail.replace("Synthetic ","").replace("synthetic ","")
            if row.id in core_flights:
                match=re.search(r"(\d+)$",row.flight)
                num=match.group(1) if match else row.flight.rsplit("-",1)[-1]
                row.flight=f"{core_flights[row.id]} {num}"
                row.airline=AIRLINES[core_flights[row.id]]
            elif row.id.startswith("INDEMO01"):
                idx=int(row.id[-4:])-100
                code=["AI","6E","IX","QP","SG"][idx%5]
                row.flight=f"{code} {5000+idx}"
                row.airline=AIRLINES[code]
                row.legs=generated_legs(idx,row.origin,row.destination,airports)
        for alt in db.query(Alternative).all():
            alt.reason="Meets route and schedule requirements" if alt.eligible else "Does not meet route, schedule or eligibility requirements"
            if alt.flight.startswith("DEMO-FY-"):
                number=alt.flight.rsplit("-",1)[-1]
                parent=db.get(Case,alt.case_id)
                code=carrier_codes.get(parent.airline,"AI") if parent else "AI"
                alt.flight=f"{code} {number}"
            elif alt.flight.startswith("DEMO-ALT-"):
                pieces=alt.flight.split("-");idx=int(pieces[2])-5000;seq=int(pieces[3])-1
                code=["AI","6E","IX","QP","SG"][(idx+seq+1)%5]
                alt.flight=f"{code} {7000+idx*3+seq:04d}"
        db.commit()
    finally: db.close()
if __name__=="__main__": seed()
