import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from app.db.database import Base

class IntakeSession(Base):
    __tablename__ = "intake_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    patient_name = Column(String, nullable=True) # Optional for now
    
    # Original Data
    transcript = Column(Text, nullable=False)
    detected_language = Column(String, default="en")
    
    # Extracted Data
    chief_complaint = Column(Text, nullable=True)
    
    # SOAP Sections
    soap_subjective = Column(Text, nullable=True)
    soap_objective = Column(Text, nullable=True)
    soap_assessment = Column(Text, nullable=True)
    soap_plan = Column(Text, nullable=True)
