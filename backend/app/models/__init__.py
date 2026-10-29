from sqlalchemy import String, Text, Integer, Boolean, ForeignKey, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
from app.db import Base

def now(): return datetime.now(timezone.utc)
class Case(Base):
    __tablename__="cases"
    id: Mapped[str]=mapped_column(String,primary_key=True)
    passenger_label: Mapped[str]=mapped_column(String)
    flight: Mapped[str]=mapped_column(String)
    airline: Mapped[str]=mapped_column(String)
    origin: Mapped[str]=mapped_column(String)
    destination: Mapped[str]=mapped_column(String)
    disruption: Mapped[str]=mapped_column(String)
    detail: Mapped[str]=mapped_column(Text)
    evidence_complete: Mapped[bool]=mapped_column(Boolean,default=True)
    review_required: Mapped[bool]=mapped_column(Boolean,default=False)
    legs: Mapped[dict]=mapped_column(JSON)
class Alternative(Base):
    __tablename__="alternatives"
    id: Mapped[int]=mapped_column(Integer,primary_key=True,autoincrement=True)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id"),index=True)
    flight: Mapped[str]=mapped_column(String)
    origin: Mapped[str]=mapped_column(String)
    destination: Mapped[str]=mapped_column(String)
    departure: Mapped[str]=mapped_column(String)
    arrival: Mapped[str]=mapped_column(String)
    eligible: Mapped[bool]=mapped_column(Boolean,default=True)
    reason: Mapped[str]=mapped_column(String,default="Meets synthetic demo criteria")
class Run(Base):
    __tablename__="runs"
    id: Mapped[str]=mapped_column(String,primary_key=True)
    case_id: Mapped[str]=mapped_column(ForeignKey("cases.id"))
    status: Mapped[str]=mapped_column(String)
    report: Mapped[dict]=mapped_column(JSON)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    trace: Mapped[list]=mapped_column(JSON,default=list)
class Recommendation(Base):
    __tablename__="recommendations"
    id: Mapped[str]=mapped_column(String,primary_key=True)
    run_id: Mapped[str]=mapped_column(ForeignKey("runs.id"))
    status: Mapped[str]=mapped_column(String,default="awaiting_human_review")
    decision: Mapped[str|None]=mapped_column(String,nullable=True)
    reviewed_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
