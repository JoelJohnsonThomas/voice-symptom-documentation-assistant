import uuid
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
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

    # Encryption tracking
    is_encrypted = Column(Boolean, default=False, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    role = Column(String, index=True, nullable=False)
    hashed_password = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # Phase 4: MFA
    totp_secret = Column(Text, nullable=True)
    mfa_enrolled_at = Column(DateTime, nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True, index=True)
    role = Column(String, nullable=True, index=True)
    action = Column(String, nullable=False)
    resource = Column(String, nullable=False)
    resource_id = Column(String, nullable=True)
    endpoint = Column(String, nullable=False, index=True)
    http_method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    # Enhanced HIPAA fields
    data_access_type = Column(String, nullable=True, index=True)  # read, write, export, delete, purge
    phi_accessed = Column(Boolean, default=False, nullable=False)
    correlation_id = Column(String, nullable=True, index=True)


class ConversationSession(Base):
    """Stores AI Voice Assistant conversation sessions."""
    __tablename__ = "conversation_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    ended_at = Column(DateTime, nullable=True)
    intake_session_id = Column(String, nullable=True, index=True)
    mode = Column(String, nullable=False, default="patient")  # "patient" or "clinician"
    state = Column(String, default="greeting")
    turns_json = Column(Text, nullable=True)  # JSON array of conversation turns
    accumulated_transcript = Column(Text, nullable=True)
    entities_json = Column(Text, nullable=True)  # JSON of extracted entities
    is_encrypted = Column(Boolean, default=False, nullable=False)


class RefreshToken(Base):
    """Stores hashed refresh tokens for JWT auth."""
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    ip_address = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)


class ConsentRecord(Base):
    """Records patient verbal/written consent before intake processing."""
    __tablename__ = "consent_records"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, nullable=False, index=True)
    patient_identifier = Column(String, nullable=True)
    consent_type = Column(String, nullable=False, default="verbal")  # verbal, written, electronic
    consented_at = Column(DateTime, default=datetime.utcnow)
    recorded_by_user_id = Column(String, nullable=True)
    recorded_by_username = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    revoked = Column(Boolean, default=False, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


class DataExportLog(Base):
    """Tracks all data exports for HIPAA compliance — who exported what, when, and where."""
    __tablename__ = "data_export_logs"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    user_id = Column(String, nullable=True, index=True)
    username = Column(String, nullable=True, index=True)
    export_type = Column(String, nullable=False)  # fhir, csv, json, pdf
    resource_type = Column(String, nullable=False)  # session, audit_log, report
    resource_ids = Column(Text, nullable=True)  # JSON list of exported resource IDs
    record_count = Column(Integer, default=0)
    destination = Column(String, nullable=True)  # e.g., "ehr_endpoint", "download", "api"
    ip_address = Column(String, nullable=True)
    status = Column(String, default="success")  # success, failed, partial
    details = Column(Text, nullable=True)
