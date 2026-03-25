"""
Pydantic request/response schemas.

Extracted from main.py for cleaner separation of concerns.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel


class TranscriptionResponse(BaseModel):
    transcript: str
    duration_seconds: float
    detected_language: Optional[str] = "en"


class FollowupQA(BaseModel):
    question: str
    answer: str = ""


class DocumentationRequest(BaseModel):
    transcript: str
    image_findings: Optional[str] = None
    followup_qa: Optional[List[FollowupQA]] = None


class DocumentationResponse(BaseModel):
    documentation: dict
    extracted_entities: dict
    requires_clinician_review: bool
    compliance_notice: str
    compliance_metadata: dict
    icd10_suggestions: Optional[list] = None
    drug_interactions: Optional[list] = None
    hallucination_check: Optional[dict] = None


class VoiceIntakeResponse(BaseModel):
    transcript: str
    documentation: dict
    extracted_entities: dict
    duration_seconds: float
    requires_clinician_review: bool
    compliance_notice: str
    compliance_metadata: dict
    detected_language: Optional[str] = "en"
    icd10_suggestions: Optional[list] = None
    drug_interactions: Optional[list] = None
    hallucination_check: Optional[dict] = None


class FHIRExportRequest(BaseModel):
    documentation: dict
    extracted_entities: Optional[dict] = None
    patient_info: Optional[dict] = None


class FHIRPushRequest(BaseModel):
    documentation: dict
    extracted_entities: Optional[dict] = None
    patient_info: Optional[dict] = None
    ehr_url: str
    auth_token: Optional[str] = None


class SessionResponse(BaseModel):
    id: str
    created_at: datetime
    patient_name: Optional[str] = None
    transcript: str
    detected_language: str
    chief_complaint: Optional[str] = None
    soap_subjective: Optional[str] = None
    soap_objective: Optional[str] = None
    soap_assessment: Optional[str] = None
    soap_plan: Optional[str] = None

    class Config:
        from_attributes = True


class SessionCreateRequest(BaseModel):
    patient_name: Optional[str] = None
    transcript: str
    detected_language: str = "en"
    chief_complaint: Optional[str] = None
    soap_subjective: Optional[str] = None
    soap_objective: Optional[str] = None
    soap_assessment: Optional[str] = None
    soap_plan: Optional[str] = None
    organization_id: Optional[str] = None
    provider_id: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: str
    timestamp: datetime
    user_id: Optional[str] = None
    username: Optional[str] = None
    role: Optional[str] = None
    action: str
    resource: str
    resource_id: Optional[str] = None
    endpoint: str
    http_method: str
    status_code: int
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    details: Optional[str] = None

    class Config:
        from_attributes = True


class IntakeQuestionsRequest(BaseModel):
    transcript: str
    detected_language: Optional[str] = "en"


class IntakeQuestionsResponse(BaseModel):
    questions: list
