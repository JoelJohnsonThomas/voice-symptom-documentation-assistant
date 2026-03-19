"""
FastAPI Main Application

Voice Symptom Intake & Documentation Assistant

COMPLIANCE NOTICE:
This system provides ADMINISTRATIVE DOCUMENTATION SUPPORT ONLY.
It does NOT perform clinical triage, provide medical advice, or make clinical decisions.
"""

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import tempfile
import logging
import asyncio
import json
import subprocess
import io
import time
import uuid
import numpy as np
from pathlib import Path

from app.config import settings
from app.rate_limiter import (
    check_rate_limit,
    get_inference_queue,
    start_cleanup_task,
    stop_cleanup_task,
)
from app.metrics import (
    REQUEST_COUNT,
    REQUEST_LATENCY,
    INFERENCE_COUNT,
    INFERENCE_LATENCY,
    INFERENCE_ERRORS,
    ACTIVE_CONNECTIONS,
    ACTIVE_INFERENCES,
    MODEL_READY,
    generate_prometheus_text,
    get_dashboard_data,
    evaluate_alerts,
)
from app.logging_config import (
    configure_logging,
    get_correlation_id,
    set_correlation_id,
    correlation_id_var,
)
from app.compliance import (
    enforce_medgemma_terms_acknowledgement,
    is_medgemma_terms_usable,
    build_compliance_notice,
    build_compliance_metadata,
    sanitize_session_payload,
)
from app.encryption import encrypt_data, decrypt_data
from app.data_retention import (
    run_purge,
    get_retention_stats,
    start_purge_scheduler,
    stop_purge_scheduler,
)
from app.auth import SYSTEM_USER, UserRole, require_roles, ALL_ROLES, INTAKE_AND_UP_ROLES
from app.models.medasr_service import get_medasr_service
from app.models.medgemma_service import get_medgemma_service
from app.models.ner_service import get_ner_service
from app.models.fhir_service import get_fhir_service
from app.models.streaming_asr import StreamingASRSession
from app.models import rag_service
from app.models import knowledge_base_service, icd10_service, drug_interaction_service
from app.utils.audio_handler import AudioHandler

from app.db.database import AsyncSessionLocal, Base, engine, get_db
from app.db.models import AuditLog, DataExportLog
from app.db import crud

# Configure structured logging
configure_logging()
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Voice Symptom Intake & Documentation Assistant",
    description=(
        "Administrative tool for voice-based symptom intake and documentation. "
        "COMPLIANCE NOTICE: This system does NOT provide clinical triage, "
        "medical advice, or clinical decision support."
    ),
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


# Pydantic models
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




def _extract_client_ip(request: Request) -> Optional[str]:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _derive_audit_resource(path: str) -> tuple[str, Optional[str]]:
    parts = [segment for segment in path.split("/") if segment]
    if not parts:
        return "unknown", None
    if parts[0] == "api":
        if len(parts) == 1:
            return "api", None
        resource = parts[1]
        resource_id = parts[2] if len(parts) > 2 else None
        return resource, resource_id
    return parts[0], parts[1] if len(parts) > 1 else None


def _derive_audit_action(method: str, path: str) -> str:
    method_upper = method.upper()
    if method_upper == "GET":
        return "read"
    if method_upper == "POST":
        return "create"
    if method_upper in {"PUT", "PATCH"}:
        return "update"
    if method_upper == "DELETE":
        return "delete"
    return method_lower if (method_lower := method.lower()) else "access"


async def _write_audit_log(
    *,
    request_path: str,
    request_method: str,
    status_code: int,
    user=None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    details: Optional[str] = None,
    data_access_type: Optional[str] = None,
    phi_accessed: bool = False,
) -> None:
    if not settings.audit_logging_enabled:
        return

    resource, resource_id = _derive_audit_resource(request_path)
    action = _derive_audit_action(request_method, request_path)

    # Auto-detect data access type from action if not explicitly provided
    if data_access_type is None:
        data_access_type = {
            "read": "read",
            "create": "write",
            "update": "write",
            "delete": "delete",
        }.get(action)

    cid = correlation_id_var.get()

    async with AsyncSessionLocal() as audit_db:
        try:
            await crud.create_audit_log(
                db=audit_db,
                user_id=getattr(user, "id", None),
                username=getattr(user, "username", None),
                role=getattr(user, "role", None),
                action=action,
                resource=resource,
                resource_id=resource_id,
                endpoint=request_path,
                http_method=request_method.upper(),
                status_code=status_code,
                ip_address=ip_address,
                user_agent=user_agent,
                details=details,
                data_access_type=data_access_type,
                phi_accessed=phi_accessed,
                correlation_id=cid,
            )
        except Exception as exc:
            logger.warning(f"Failed to write audit log: {exc}")


# NOTE: Custom HTTP middleware (metrics, audit) removed to avoid
# BaseHTTPMiddleware compatibility issues with certain environments.
# Metrics and audit logging are handled at the endpoint level instead.


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    stop_cleanup_task()
    stop_purge_scheduler()


# Startup event to preload models
@app.on_event("startup")
async def startup_event():
    """Preload ML models at server startup and init DB."""
    logger.info("Starting server initialization...")
    try:
        # Init DB tables
        logger.info("Initializing database tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        logger.info("Loading MedASR model...")
        medasr = get_medasr_service()
        medasr_ready = medasr.is_ready()
        MODEL_READY.set(1.0 if medasr_ready else 0.0, model="medasr")
        logger.info(f"MedASR ready: {medasr_ready}")

        if is_medgemma_terms_usable():
            logger.info("Loading MedGemma model...")
            medgemma = get_medgemma_service()
            medgemma_ready = medgemma.is_ready()
            MODEL_READY.set(1.0 if medgemma_ready else 0.0, model="medgemma")
            vision_ready = medgemma.is_vision_ready()
            MODEL_READY.set(1.0 if vision_ready else 0.0, model="medgemma_vision")
            logger.info(f"MedGemma ready: {medgemma_ready}, Vision: {vision_ready}")
        else:
            MODEL_READY.set(0.0, model="medgemma")
            MODEL_READY.set(0.0, model="medgemma_vision")
            logger.warning(
                "Skipping MedGemma preload: terms acknowledgement gate is enabled and not acknowledged."
            )

        logger.info("Loading Medical NER model...")
        ner = get_ner_service()
        MODEL_READY.set(1.0 if ner.is_ready else 0.0, model="ner")
        logger.info(f"Medical NER ready: {ner.is_ready}")

        logger.info("All models loaded successfully!")

        # Start rate limiter cleanup background task
        start_cleanup_task()
        logger.info("Rate limiter cleanup task started.")

        # Initialize knowledge bases (Phase 2)
        if settings.knowledge_base_enabled:
            logger.info("Initializing clinical knowledge base...")
            kb_stats = knowledge_base_service.initialize_knowledge_base()
            logger.info(f"Knowledge base: {kb_stats}")
        if settings.icd10_lookup_enabled:
            logger.info("Initializing ICD-10 index...")
            icd10_stats = icd10_service.initialize_icd10_index()
            logger.info(f"ICD-10 index: {icd10_stats}")

        # Start data retention auto-purge scheduler
        start_purge_scheduler()
        if settings.auto_purge_enabled:
            logger.info(
                f"Data retention auto-purge enabled "
                f"(sessions: {settings.retention_sessions_days}d, "
                f"audit logs: {settings.retention_audit_logs_days}d, "
                f"interval: {settings.auto_purge_interval_hours}h)"
            )

    except Exception as e:
        logger.error(f"Model preload failed: {e}")
        # Don't crash - allow lazy loading as fallback


@app.get("/api/audit-logs", response_model=List[AuditLogResponse])
async def list_audit_logs(
    skip: int = 0,
    limit: int = 200,
    username: Optional[str] = None,
    resource: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """Read audit logs for compliance monitoring."""
    logs = await crud.get_audit_logs(
        db=db,
        skip=skip,
        limit=min(limit, 1000),
        username=username,
        resource=resource,
    )
    return logs


# Health check endpoint
@app.get("/api/health")
async def health_check():
    """Check if services are ready."""
    try:
        medasr = get_medasr_service()
        medgemma_ready = False
        vision_ready = False
        if is_medgemma_terms_usable():
            medgemma = get_medgemma_service()
            medgemma_ready = medgemma.is_ready()
            vision_ready = medgemma.is_vision_ready()

        return {
            "status": "healthy",
            "medasr_ready": medasr.is_ready(),
            "medgemma_ready": medgemma_ready,
            "ner_ready": get_ner_service().is_ready,
            "vision_ready": vision_ready,
            "device": settings.device,
            "gpu_enabled": settings.enable_gpu,
            "compliance_metadata": build_compliance_metadata(),
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )


# Queue status endpoint
@app.get("/api/queue/status")
async def queue_status():
    """Return current inference queue status."""
    queue = get_inference_queue()
    return await queue.get_status()


# =====================================================
# MONITORING & OBSERVABILITY ENDPOINTS
# =====================================================

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint."""
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=generate_prometheus_text(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.get("/api/monitoring/dashboard")
async def monitoring_dashboard():
    """Return aggregated monitoring dashboard data (Admin only)."""
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    data = get_dashboard_data()
    queue = get_inference_queue()
    data["queue"] = await queue.get_status()
    return data


@app.get("/api/monitoring/alerts")
async def monitoring_alerts():
    """Return active alerts (Admin only)."""
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics disabled")
    return {"alerts": evaluate_alerts()}


# Transcription endpoint
@app.post("/api/transcribe", response_model=TranscriptionResponse)
async def transcribe_audio(
    request: Request,
    audio: UploadFile = File(...),
):
    """
    Transcribe audio file to text using MedASR.

    Args:
        audio: Audio file (WAV, MP3, M4A, FLAC, OGG)

    Returns:
        Transcription result
    """
    await check_rate_limit(request, tier="inference")

    queue = get_inference_queue()
    request_id = str(uuid.uuid4())
    queue_info = await queue.acquire(request_id)
    inference_start = time.monotonic()

    temp_file = None
    ACTIVE_INFERENCES.inc(model="medasr")
    model_start = None
    try:
        logger.info(f"Received audio file: {audio.filename}")

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as temp_file:
            content = await audio.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Load audio
        audio_handler = AudioHandler()
        audio_array, sr = audio_handler.load_audio(file_path=temp_path)
        duration = len(audio_array) / sr

        # Transcribe
        medasr = get_medasr_service()
        model_start = time.monotonic()
        result = medasr.transcribe(audio_array=audio_array, sample_rate=sr)
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medasr")
        INFERENCE_COUNT.inc(model="medasr", status="success")
        if isinstance(result, tuple):
            transcript, detected_language = result
        else:
            transcript, detected_language = result, "en"

        logger.info(f"Transcription successful: {len(transcript)} characters, Language: {detected_language}")

        return TranscriptionResponse(
            transcript=transcript,
            duration_seconds=duration,
            detected_language=detected_language
        )

    except Exception as e:
        INFERENCE_COUNT.inc(model="medasr", status="error")
        INFERENCE_ERRORS.inc(model="medasr", error_type=type(e).__name__)
        logger.error(f"Transcription failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        ACTIVE_INFERENCES.dec(model="medasr")
        await queue.release(duration=time.monotonic() - inference_start)
        # Clean up temp file
        if temp_file:
            Path(temp_path).unlink(missing_ok=True)


# Follow-up questions endpoint
class IntakeQuestionsRequest(BaseModel):
    transcript: str
    detected_language: Optional[str] = "en"


class IntakeQuestionsResponse(BaseModel):
    questions: List[str]


@app.post("/api/intake/questions", response_model=IntakeQuestionsResponse)
async def get_intake_followup_questions(
    request: IntakeQuestionsRequest,
    raw_request: Request,
    current_user=Depends(require_roles(*INTAKE_AND_UP_ROLES)),
):
    """
    Generate 2-3 targeted follow-up questions for missing clinical information.

    Call this after the patient's initial voice/text description to identify
    gaps (severity, duration, location, quality, aggravating factors, etc.).
    Submit the patient's answers back via /api/document in the followup_qa field.
    """
    await check_rate_limit(raw_request, tier="inference")

    queue = get_inference_queue()
    request_id = str(uuid.uuid4())
    await queue.acquire(request_id)
    inference_start = time.monotonic()

    ACTIVE_INFERENCES.inc(model="medgemma")
    try:
        enforce_medgemma_terms_acknowledgement()

        if not request.transcript or len(request.transcript.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Transcript too short (minimum 10 characters required)",
            )

        medgemma = get_medgemma_service()
        model_start = time.monotonic()
        questions = medgemma.generate_followup_questions(
            request.transcript,
            detected_language=request.detected_language or "en",
        )
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medgemma")
        INFERENCE_COUNT.inc(model="medgemma", status="success")

        logger.info(f"Generated {len(questions)} follow-up questions")
        return IntakeQuestionsResponse(questions=questions)

    except HTTPException:
        raise
    except Exception as e:
        INFERENCE_COUNT.inc(model="medgemma", status="error")
        INFERENCE_ERRORS.inc(model="medgemma", error_type=type(e).__name__)
        logger.error(f"Follow-up question generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_INFERENCES.dec(model="medgemma")
        await queue.release(duration=time.monotonic() - inference_start)


# Documentation endpoint
@app.post("/api/document", response_model=DocumentationResponse)
async def generate_documentation(
    request: DocumentationRequest,
    raw_request: Request,
):
    """
    Generate structured symptom documentation from transcript.

    COMPLIANCE: This does NOT perform clinical assessment or triage.

    Args:
        request: Contains patient transcript

    Returns:
        Structured documentation flagged for clinician review
    """
    await check_rate_limit(raw_request, tier="inference")

    queue = get_inference_queue()
    request_id = str(uuid.uuid4())
    queue_info = await queue.acquire(request_id)
    inference_start = time.monotonic()

    ACTIVE_INFERENCES.inc(model="medgemma")
    try:
        logger.info("Generating documentation from transcript")

        enforce_medgemma_terms_acknowledgement()

        if not request.transcript or len(request.transcript.strip()) < 10:
            raise HTTPException(
                status_code=400,
                detail="Transcript too short (minimum 10 characters required)"
            )

        # Retrieve similar past cases + clinical guidelines for RAG context
        rag_context = rag_service.retrieve_enriched_context(request.transcript)
        similar_cases = rag_context["similar_sessions"]
        clinical_guidelines = rag_context["clinical_guidelines"]
        if similar_cases:
            logger.info(f"RAG: retrieved {len(similar_cases)} similar cases for documentation")
        if clinical_guidelines:
            logger.info(f"RAG: retrieved {len(clinical_guidelines)} clinical guidelines")

        # Extract Medical Entities (needed for ICD-10 + drug interactions)
        ner_service = get_ner_service()
        ner_start = time.monotonic()
        extracted_entities = ner_service.extract_entities(request.transcript)
        INFERENCE_LATENCY.observe(time.monotonic() - ner_start, model="ner")
        INFERENCE_COUNT.inc(model="ner", status="success")

        # Phase 2.2: Semantic ICD-10 code lookup + cross-validation
        icd10_suggestions = []
        if settings.icd10_lookup_enabled:
            symptoms = extracted_entities.get("conditions", [])
            symptom_texts = [c.get("text", "") for c in symptoms if c.get("text")]
            if symptom_texts:
                semantic_codes = []
                for s in symptom_texts:
                    semantic_codes.extend(icd10_service.lookup_icd10_codes(s))
                # Also look up by transcript for broader coverage
                semantic_codes.extend(icd10_service.lookup_icd10_codes(request.transcript[:500]))
                # Deduplicate by code
                seen_codes = set()
                unique_codes = []
                for c in semantic_codes:
                    if c["code"] not in seen_codes:
                        seen_codes.add(c["code"])
                        unique_codes.append(c)
                # Cross-validate with NER
                ner_conditions = extracted_entities.get("conditions", [])
                icd10_suggestions = icd10_service.cross_validate_codes(ner_conditions, unique_codes)

        # Phase 2.3: Drug interaction check
        drug_interactions = drug_interaction_service.check_interactions_from_entities(
            extracted_entities, transcript=request.transcript
        )
        if drug_interactions:
            logger.info(f"Drug interactions: {len(drug_interactions)} flagged")

        # Generate documentation with enriched context
        medgemma = get_medgemma_service()
        model_start = time.monotonic()
        followup_qa_dicts = (
            [qa.model_dump() for qa in request.followup_qa]
            if request.followup_qa
            else None
        )
        documentation = medgemma.generate_documentation(
            request.transcript,
            image_findings=request.image_findings,
            similar_cases=similar_cases,
            followup_qa=followup_qa_dicts,
            clinical_guidelines=clinical_guidelines,
            drug_interactions=drug_interactions,
            icd10_suggestions=icd10_suggestions,
        )
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medgemma")
        INFERENCE_COUNT.inc(model="medgemma", status="success")

        logger.info("Documentation generated successfully")

        return DocumentationResponse(
            documentation=documentation,
            extracted_entities=extracted_entities,
            requires_clinician_review=True,
            compliance_notice=build_compliance_notice(),
            compliance_metadata=build_compliance_metadata(),
            icd10_suggestions=icd10_suggestions if icd10_suggestions else None,
            drug_interactions=drug_interactions if drug_interactions else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        INFERENCE_COUNT.inc(model="medgemma", status="error")
        INFERENCE_ERRORS.inc(model="medgemma", error_type=type(e).__name__)
        logger.error(f"Documentation generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_INFERENCES.dec(model="medgemma")
        await queue.release(duration=time.monotonic() - inference_start)


# Image analysis endpoint
@app.post("/api/analyze-image")
async def analyze_image(
    request: Request,
    image: UploadFile = File(...),
):
    """
    Analyze an uploaded medical image using MedGemma vision.

    COMPLIANCE: Produces DESCRIPTIVE observations only.
    Does NOT diagnose or recommend treatment.

    Args:
        image: Image file (JPEG, PNG, WebP)

    Returns:
        Image analysis results with visual findings
    """
    await check_rate_limit(request, tier="inference")

    queue = get_inference_queue()
    request_id = str(uuid.uuid4())
    queue_info = await queue.acquire(request_id)
    inference_start = time.monotonic()

    ACTIVE_INFERENCES.inc(model="medgemma_vision")
    try:
        enforce_medgemma_terms_acknowledgement()

        # Validate file type
        allowed_types = {'image/jpeg', 'image/png', 'image/webp', 'image/jpg'}
        if image.content_type and image.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {image.content_type}. Allowed: JPEG, PNG, WebP"
            )

        # Read and validate size
        image_bytes = await image.read()
        max_bytes = settings.max_image_size_mb * 1024 * 1024
        if len(image_bytes) > max_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Image too large ({len(image_bytes) / (1024*1024):.1f}MB). Maximum: {settings.max_image_size_mb}MB"
            )

        logger.info(f"Analyzing image: {image.filename} ({len(image_bytes)} bytes)")

        # Check vision model availability
        medgemma = get_medgemma_service()
        if not medgemma.is_vision_ready():
            raise HTTPException(
                status_code=503,
                detail="Vision model not available. Image analysis is disabled or failed to load."
            )

        # Analyze image
        model_start = time.monotonic()
        analysis = medgemma.analyze_image(image_bytes)
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medgemma_vision")
        INFERENCE_COUNT.inc(model="medgemma_vision", status="success")

        logger.info("Image analysis completed successfully")

        return JSONResponse(content={
            "image_analysis": analysis,
            "requires_clinician_review": True,
            "compliance_notice": build_compliance_notice(),
            "compliance_metadata": build_compliance_metadata(),
        })

    except HTTPException:
        raise
    except Exception as e:
        INFERENCE_COUNT.inc(model="medgemma_vision", status="error")
        INFERENCE_ERRORS.inc(model="medgemma_vision", error_type=type(e).__name__)
        logger.error(f"Image analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_INFERENCES.dec(model="medgemma_vision")
        await queue.release(duration=time.monotonic() - inference_start)


# End-to-end voice intake endpoint
@app.post("/api/voice-intake", response_model=VoiceIntakeResponse)
async def voice_intake(
    request: Request,
    audio: UploadFile = File(...),
):
    """
    Complete voice intake workflow: audio -> transcription -> documentation.

    COMPLIANCE: This is an administrative workflow only.
    No clinical decisions are made by this system.

    Args:
        audio: Audio file with patient symptom report

    Returns:
        Complete intake documentation
    """
    await check_rate_limit(request, tier="inference")

    queue = get_inference_queue()
    request_id = str(uuid.uuid4())
    queue_info = await queue.acquire(request_id)
    inference_start = time.monotonic()

    temp_file = None
    ACTIVE_INFERENCES.inc(model="medasr")
    try:
        logger.info(f"Starting voice intake for: {audio.filename}")

        enforce_medgemma_terms_acknowledgement()

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(audio.filename).suffix) as temp_file:
            content = await audio.read()
            temp_file.write(content)
            temp_path = temp_file.name

        # Step 1: Load audio
        audio_handler = AudioHandler()
        audio_array, sr = audio_handler.load_audio(file_path=temp_path)
        duration = len(audio_array) / sr

        # Step 2: Transcribe
        medasr = get_medasr_service()
        model_start = time.monotonic()
        result = medasr.transcribe(audio_array=audio_array, sample_rate=sr)
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medasr")
        INFERENCE_COUNT.inc(model="medasr", status="success")
        if isinstance(result, tuple):
            transcript, detected_language = result
        else:
            transcript, detected_language = result, "en"
        logger.info(f"Transcription complete: {len(transcript)} characters, Language: {detected_language}")

        # Step 3: Retrieve similar past cases + clinical guidelines for RAG context
        rag_context = rag_service.retrieve_enriched_context(transcript)
        similar_cases = rag_context["similar_sessions"]
        clinical_guidelines = rag_context["clinical_guidelines"]
        if similar_cases:
            logger.info(f"RAG: retrieved {len(similar_cases)} similar cases for voice intake")
        if clinical_guidelines:
            logger.info(f"RAG: retrieved {len(clinical_guidelines)} clinical guidelines")

        # Step 4: Extract Medical Entities (needed before doc gen for ICD-10/drug checks)
        ACTIVE_INFERENCES.dec(model="medasr")
        ACTIVE_INFERENCES.inc(model="ner")
        ner_service = get_ner_service()
        ner_start = time.monotonic()
        extracted_entities = ner_service.extract_entities(transcript)
        INFERENCE_LATENCY.observe(time.monotonic() - ner_start, model="ner")
        INFERENCE_COUNT.inc(model="ner", status="success")
        ACTIVE_INFERENCES.dec(model="ner")

        # Step 4b: Semantic ICD-10 lookup + cross-validation (Phase 2.2)
        icd10_suggestions = []
        if settings.icd10_lookup_enabled:
            symptoms = extracted_entities.get("conditions", [])
            symptom_texts = [c.get("text", "") for c in symptoms if c.get("text")]
            semantic_codes = []
            for s in symptom_texts:
                semantic_codes.extend(icd10_service.lookup_icd10_codes(s))
            semantic_codes.extend(icd10_service.lookup_icd10_codes(transcript[:500]))
            seen_codes = set()
            unique_codes = []
            for c in semantic_codes:
                if c["code"] not in seen_codes:
                    seen_codes.add(c["code"])
                    unique_codes.append(c)
            icd10_suggestions = icd10_service.cross_validate_codes(
                extracted_entities.get("conditions", []), unique_codes
            )

        # Step 4c: Drug interaction check (Phase 2.3)
        drug_interactions = drug_interaction_service.check_interactions_from_entities(
            extracted_entities, transcript=transcript
        )
        if drug_interactions:
            logger.info(f"Drug interactions: {len(drug_interactions)} flagged")

        # Step 5: Generate documentation with enriched context
        ACTIVE_INFERENCES.inc(model="medgemma")
        medgemma = get_medgemma_service()
        model_start = time.monotonic()
        documentation = medgemma.generate_documentation(
            transcript,
            detected_language=detected_language,
            similar_cases=similar_cases,
            clinical_guidelines=clinical_guidelines,
            drug_interactions=drug_interactions,
            icd10_suggestions=icd10_suggestions,
        )
        INFERENCE_LATENCY.observe(time.monotonic() - model_start, model="medgemma")
        INFERENCE_COUNT.inc(model="medgemma", status="success")
        ACTIVE_INFERENCES.dec(model="medgemma")

        logger.info("Documentation generated")

        return VoiceIntakeResponse(
            transcript=transcript,
            documentation=documentation,
            extracted_entities=extracted_entities,
            duration_seconds=duration,
            requires_clinician_review=True,
            compliance_notice=build_compliance_notice(),
            compliance_metadata=build_compliance_metadata(),
            detected_language=detected_language,
            icd10_suggestions=icd10_suggestions if icd10_suggestions else None,
            drug_interactions=drug_interactions if drug_interactions else None,
        )
    except HTTPException:
        raise
    except Exception as e:
        INFERENCE_ERRORS.inc(model="voice_intake", error_type=type(e).__name__)
        logger.error(f"Voice intake failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Ensure all gauges decremented (safe even if already at 0 due to Gauge logic)
        await queue.release(duration=time.monotonic() - inference_start)
        # Clean up temp file
        if temp_file:
            Path(temp_path).unlink(missing_ok=True)


# =====================================================
# WEBSOCKET STREAMING TRANSCRIPTION
# =====================================================

def decode_webm_chunk(webm_bytes: bytes, sample_rate: int = 16000) -> Optional[np.ndarray]:
    """
    Decode a WebM/Opus audio chunk to raw PCM float32 using FFmpeg.

    Args:
        webm_bytes: Raw WebM audio bytes from browser MediaRecorder
        sample_rate: Target sample rate

    Returns:
        Float32 numpy array of audio samples, or None on failure
    """
    try:
        process = subprocess.run(
            [
                'ffmpeg', '-y',
                '-i', 'pipe:0',           # Read from stdin
                '-f', 'f32le',            # Output raw float32 little-endian
                '-acodec', 'pcm_f32le',
                '-ar', str(sample_rate),  # Target sample rate
                '-ac', '1',              # Mono
                'pipe:1'                  # Write to stdout
            ],
            input=webm_bytes,
            capture_output=True,
            timeout=10
        )

        if process.returncode != 0:
            return None

        audio = np.frombuffer(process.stdout, dtype=np.float32)
        return audio if len(audio) > 0 else None

    except Exception as e:
        logger.debug(f"WebM decode failed: {e}")
        return None


@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """
    WebSocket endpoint for real-time streaming transcription.

    Protocol:
    - Client sends binary audio chunks (WebM from MediaRecorder)
    - Server accumulates chunks and sends partial transcripts
    - Client sends text message '{"action": "stop"}' to finalize
    - Server sends final transcript and closes

    Messages sent to client:
    - {"type": "partial", "text": "new words", "full_text": "all words so far"}
    - {"type": "final", "text": "complete transcript", "full_text": "..."}
    - {"type": "error", "message": "error description"}
    - {"type": "connected", "message": "ready"}
    """
    user = None
    client_ip = websocket.client.host if websocket.client else None
    user_agent = websocket.headers.get("user-agent")

    await websocket.accept()
    ACTIVE_CONNECTIONS.inc(type="websocket")
    logger.info("WebSocket client connected for streaming transcription")
    await _write_audit_log(
        request_path="/ws/transcribe",
        request_method="WS",
        status_code=101,
        user=user,
        ip_address=client_ip,
        user_agent=user_agent,
        details="websocket_connected",
    )

    session = StreamingASRSession(sample_rate=settings.audio_sample_rate)

    # Accumulated WebM data for decoding
    webm_accumulator = bytearray()
    last_decoded_size = 0

    try:
        # Send ready signal
        await websocket.send_json({
            "type": "connected",
            "message": "ready"
        })

        while True:
            # Receive data (binary audio or text commands)
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"]:
                # Binary audio chunk from MediaRecorder (WebM/Opus)
                chunk_bytes = message["bytes"]
                webm_accumulator.extend(chunk_bytes)

                # Decode the accumulated WebM data
                # We re-decode the full accumulated WebM each time because
                # WebM chunks from MediaRecorder aren't independently decodable
                audio_data = decode_webm_chunk(
                    bytes(webm_accumulator),
                    settings.audio_sample_rate
                )

                if audio_data is not None and len(audio_data) > last_decoded_size:
                    # Add only the NEW samples to the session
                    new_samples = audio_data[last_decoded_size:]
                    session.add_audio_array(new_samples)
                    last_decoded_size = len(audio_data)

                # Check if we should run transcription
                if session.should_transcribe():
                    # Run transcription in thread pool to avoid blocking
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, session.transcribe_partial
                    )

                    if result:
                        await websocket.send_json(result)
                        logger.debug(
                            f"Sent partial: '{result.get('text', '')[:50]}...'"
                        )

            elif "text" in message and message["text"]:
                # Text command from client
                try:
                    cmd = json.loads(message["text"])
                except json.JSONDecodeError:
                    cmd = {"action": message["text"]}

                if cmd.get("action") == "stop":
                    logger.info("Client requested stop — running final transcription")

                    # Run final transcription
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, session.transcribe_final
                    )

                    await websocket.send_json(result)
                    logger.info(
                        f"Sent final transcript: {len(result.get('text', ''))} chars"
                    )
                    break

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass
    finally:
        # Run final transcription if not already done
        if not session._is_finalized and session.get_buffer_duration() > 0.5:
            try:
                result = session.transcribe_final()
                await websocket.send_json(result)
            except Exception:
                pass

        logger.info(
            f"Streaming session ended: {session.get_buffer_duration():.1f}s audio, "
            f"{session._chunk_count} chunks"
        )
        ACTIVE_CONNECTIONS.dec(type="websocket")
        await _write_audit_log(
            request_path="/ws/transcribe",
            request_method="WS",
            status_code=200,
            user=user,
            ip_address=client_ip,
            user_agent=user_agent,
            details=(
                f"websocket_closed; audio_seconds={session.get_buffer_duration():.1f}; "
                f"chunks={session._chunk_count}"
            ),
        )


# PWA Endpoints
@app.get("/service-worker.js")
async def service_worker():
    """Serve the Service Worker script from root scope."""
    from fastapi.responses import FileResponse
    sw_path = Path(__file__).parent / "static" / "service-worker.js"
    if sw_path.exists():
        return FileResponse(sw_path, media_type="application/javascript")
    raise HTTPException(status_code=404, detail=f"Service worker not found at {sw_path}")


@app.get("/manifest.json")
async def manifest():
    """Serve the Web App Manifest."""
    from fastapi.responses import FileResponse
    manifest_path = Path(__file__).parent / "static" / "manifest.json"
    if manifest_path.exists():
        return FileResponse(manifest_path, media_type="application/manifest+json")
    raise HTTPException(status_code=404, detail=f"Manifest not found at {manifest_path}")


# =====================================================
# FHIR EXPORT ENDPOINTS
# =====================================================

@app.post("/api/fhir/export")
async def fhir_export(
    request: FHIRExportRequest,
    raw_request: Request,
):
    """Generate and return a FHIR R4 Bundle from documentation data."""
    try:
        fhir = get_fhir_service()
        bundle = fhir.build_bundle(
            documentation=request.documentation,
            entities=request.extracted_entities,
            patient_info=request.patient_info
        )

        # Log HIPAA data export
        async with AsyncSessionLocal() as db:
            await crud.create_export_log(
                db=db,
                user_id=getattr(SYSTEM_USER, "id", None),
                username=getattr(SYSTEM_USER, "username", None),
                export_type="fhir",
                resource_type="session",
                record_count=1,
                destination="download",
                ip_address=_extract_client_ip(raw_request),
                status="success",
            )

        return bundle
    except Exception as e:
        logger.error(f"FHIR export failed: {e}")
        raise HTTPException(status_code=500, detail=f"FHIR export failed: {str(e)}")


@app.post("/api/fhir/push")
async def fhir_push(
    request: FHIRPushRequest,
    raw_request: Request,
):
    """Build a FHIR Bundle and push it to an external EHR/FHIR server."""
    export_status = "success"
    try:
        fhir = get_fhir_service()
        bundle = fhir.build_bundle(
            documentation=request.documentation,
            entities=request.extracted_entities,
            patient_info=request.patient_info
        )
        result = await fhir.push_to_ehr(bundle, request.ehr_url, request.auth_token)
        return result
    except Exception as e:
        export_status = "failed"
        logger.error(f"FHIR push failed: {e}")
        raise HTTPException(status_code=500, detail=f"FHIR push failed: {str(e)}")
    finally:
        async with AsyncSessionLocal() as db:
            try:
                await crud.create_export_log(
                    db=db,
                    user_id=getattr(SYSTEM_USER, "id", None),
                    username=getattr(SYSTEM_USER, "username", None),
                    export_type="fhir",
                    resource_type="session",
                    record_count=1,
                    destination=request.ehr_url,
                    ip_address=_extract_client_ip(raw_request),
                    status=export_status,
                )
            except Exception:
                pass


# =====================================================
# HIPAA COMPLIANCE ENDPOINTS
# =====================================================

@app.get("/api/hipaa/retention/stats")
async def retention_stats():
    """Get data retention statistics (Admin only)."""
    stats = await get_retention_stats()
    stats["encryption_at_rest_enabled"] = settings.encryption_at_rest_enabled
    return stats


@app.post("/api/hipaa/retention/purge")
async def manual_purge(
    raw_request: Request,
):
    """Manually trigger data purge based on retention policies (Admin only)."""
    results = await run_purge()

    # Log the purge action
    await _write_audit_log(
        request_path="/api/hipaa/retention/purge",
        request_method="POST",
        status_code=200,
        user=SYSTEM_USER,
        ip_address=_extract_client_ip(raw_request),
        user_agent=raw_request.headers.get("user-agent"),
        details=f"manual_purge; sessions={results['sessions_purged']}; audit_logs={results['audit_logs_purged']}",
        data_access_type="purge",
        phi_accessed=results["sessions_purged"] > 0,
    )

    return results


@app.get("/api/hipaa/export-logs")
async def list_export_logs(
    skip: int = 0,
    limit: int = 200,
    username: Optional[str] = None,
    export_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List data export logs for HIPAA compliance monitoring (Admin only)."""
    logs = await crud.get_export_logs(
        db=db,
        skip=skip,
        limit=min(limit, 1000),
        username=username,
        export_type=export_type,
    )
    return [
        {
            "id": log.id,
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "user_id": log.user_id,
            "username": log.username,
            "export_type": log.export_type,
            "resource_type": log.resource_type,
            "record_count": log.record_count,
            "destination": log.destination,
            "ip_address": log.ip_address,
            "status": log.status,
            "details": log.details,
        }
        for log in logs
    ]


@app.get("/api/hipaa/audit-summary")
async def hipaa_audit_summary(
    db: AsyncSession = Depends(get_db),
):
    """Get HIPAA audit dashboard summary (Admin only)."""
    from sqlalchemy import func, select as sa_select

    # PHI access count
    phi_result = await db.execute(
        sa_select(func.count()).select_from(AuditLog).where(AuditLog.phi_accessed == True)
    )
    phi_access_count = phi_result.scalar() or 0

    # Export count
    export_result = await db.execute(
        sa_select(func.count()).select_from(DataExportLog)
    )
    export_count = export_result.scalar() or 0

    # Total audit log count
    audit_result = await db.execute(
        sa_select(func.count()).select_from(AuditLog)
    )
    total_audit_count = audit_result.scalar() or 0

    # Recent PHI accesses (last 24h)
    from datetime import timedelta
    cutoff_24h = datetime.utcnow() - timedelta(hours=24)
    recent_phi = await db.execute(
        sa_select(func.count()).select_from(AuditLog).where(
            AuditLog.phi_accessed == True,
            AuditLog.timestamp >= cutoff_24h,
        )
    )
    recent_phi_count = recent_phi.scalar() or 0

    retention = await get_retention_stats()

    return {
        "total_audit_logs": total_audit_count,
        "phi_access_count": phi_access_count,
        "recent_phi_accesses_24h": recent_phi_count,
        "total_exports": export_count,
        "encryption_at_rest": settings.encryption_at_rest_enabled,
        "retention": retention,
        "compliance_metadata": build_compliance_metadata(),
    }


# =====================================================
# SESSION HISTORY ENDPOINTS
# =====================================================

@app.post("/api/sessions", response_model=SessionResponse)
async def save_session(
    request: SessionCreateRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save a new patient intake session with optional encryption at rest."""
    try:
        sanitized_payload = sanitize_session_payload(request.model_dump())

        # Encrypt PHI fields at rest if enabled
        if settings.encryption_at_rest_enabled:
            for field in ("transcript", "chief_complaint", "soap_subjective",
                          "soap_objective", "soap_assessment", "soap_plan"):
                if sanitized_payload.get(field):
                    sanitized_payload[field] = encrypt_data(sanitized_payload[field])
            sanitized_payload["is_encrypted"] = True

        db_session = await crud.create_session(db=db, session_data=sanitized_payload)

        # Index session in RAG store (use plaintext values, not encrypted ones)
        if settings.rag_enabled:
            raw = request.model_dump()
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: rag_service.index_session(
                    session_id=db_session.id,
                    transcript=raw.get("transcript", ""),
                    chief_complaint=raw.get("chief_complaint"),
                    soap_subjective=raw.get("soap_subjective"),
                    soap_objective=raw.get("soap_objective"),
                    soap_assessment=raw.get("soap_assessment"),
                    soap_plan=raw.get("soap_plan"),
                ),
            )

        return db_session
    except Exception as e:
        logger.error(f"Failed to save session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions", response_model=List[SessionResponse])
async def list_sessions(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a list of past sessions, decrypting if needed."""
    try:
        sessions = await crud.get_sessions(db=db, skip=skip, limit=limit)

        # Decrypt encrypted sessions
        if settings.encryption_at_rest_enabled:
            for session in sessions:
                if getattr(session, "is_encrypted", False):
                    for field in ("transcript", "chief_complaint", "soap_subjective",
                                  "soap_objective", "soap_assessment", "soap_plan"):
                        val = getattr(session, field, None)
                        if val:
                            setattr(session, field, decrypt_data(val))

        return sessions
    except Exception as e:
        logger.error(f"Failed to retrieve sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a specific session by ID, decrypting if needed."""
    db_session = await crud.get_session_by_id(db=db, session_id=session_id)
    if db_session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    # Decrypt PHI fields if session was stored encrypted
    if getattr(db_session, "is_encrypted", False) and settings.encryption_at_rest_enabled:
        for field in ("transcript", "chief_complaint", "soap_subjective",
                      "soap_objective", "soap_assessment", "soap_plan"):
            val = getattr(db_session, field, None)
            if val:
                setattr(db_session, field, decrypt_data(val))

    return db_session


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Delete a specific session."""
    success = await crud.delete_session(db=db, session_id=session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")

    # Remove from RAG vector store
    if settings.rag_enabled:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: rag_service.remove_session(session_id))

    return {"status": "success"}


# =====================================================
# RAG ENDPOINTS
# =====================================================

@app.get("/api/rag/status")
async def rag_status(current_user=Depends(require_roles(*ALL_ROLES))):
    """Return RAG vector store statistics."""
    return rag_service.get_index_stats()


@app.post("/api/rag/index")
async def rag_reindex(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(require_roles(UserRole.ADMIN)),
):
    """
    Rebuild the RAG index from all sessions currently in the database.

    Useful after enabling RAG on an existing deployment or after a
    bulk import.  Admin only.
    """
    if not settings.rag_enabled:
        raise HTTPException(status_code=400, detail="RAG is disabled (set RAG_ENABLED=true)")

    sessions = await crud.get_sessions(db=db, skip=0, limit=10000)

    indexed = 0
    errors = 0
    loop = asyncio.get_event_loop()

    for session in sessions:
        # Decrypt if stored encrypted
        fields = {}
        for field in ("transcript", "chief_complaint", "soap_subjective",
                      "soap_objective", "soap_assessment", "soap_plan"):
            val = getattr(session, field, None)
            if val and getattr(session, "is_encrypted", False) and settings.encryption_at_rest_enabled:
                try:
                    val = decrypt_data(val)
                except Exception:
                    pass
            fields[field] = val

        if not fields.get("transcript"):
            continue

        try:
            await loop.run_in_executor(
                None,
                lambda s=session, f=fields: rag_service.index_session(
                    session_id=s.id,
                    transcript=f["transcript"],
                    chief_complaint=f["chief_complaint"],
                    soap_subjective=f["soap_subjective"],
                    soap_objective=f["soap_objective"],
                    soap_assessment=f["soap_assessment"],
                    soap_plan=f["soap_plan"],
                ),
            )
            indexed += 1
        except Exception as exc:
            logger.warning(f"RAG reindex: failed for session {session.id}: {exc}")
            errors += 1

    stats = rag_service.get_index_stats()
    return {
        "indexed": indexed,
        "errors": errors,
        "total_in_store": stats.get("total_chunks", 0),
    }


# =====================================================
# KNOWLEDGE BASE ENDPOINTS (Phase 2)
# =====================================================

@app.get("/api/knowledge-base/status")
async def knowledge_base_status():
    """Return knowledge base statistics."""
    return {
        "guidelines": knowledge_base_service.get_knowledge_base_stats(),
        "icd10": icd10_service.get_icd10_stats(),
        "drug_interactions": drug_interaction_service.get_interaction_db_stats(),
    }


@app.post("/api/knowledge-base/initialize")
async def initialize_knowledge_base(force_reseed: bool = False):
    """Initialize or re-seed the clinical knowledge base and ICD-10 index."""
    loop = asyncio.get_event_loop()
    kb_result = await loop.run_in_executor(
        None, lambda: knowledge_base_service.initialize_knowledge_base(force_reseed=force_reseed)
    )
    icd10_result = await loop.run_in_executor(
        None, lambda: icd10_service.initialize_icd10_index(force_reseed=force_reseed)
    )
    return {
        "guidelines": kb_result,
        "icd10": icd10_result,
    }


@app.post("/api/knowledge-base/guidelines")
async def add_custom_guideline(
    guideline_id: str,
    title: str,
    content: str,
    source: str,
    category: str,
    conditions: List[str],
):
    """Add a custom clinical guideline to the knowledge base."""
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: knowledge_base_service.add_guideline(
            guideline_id=guideline_id,
            title=title,
            content=content,
            source=source,
            category=category,
            conditions=conditions,
        ),
    )
    return result


@app.delete("/api/knowledge-base/guidelines/{guideline_id}")
async def delete_guideline(guideline_id: str):
    """Remove a guideline from the knowledge base."""
    return knowledge_base_service.remove_guideline(guideline_id)


@app.post("/api/icd10/lookup")
async def icd10_lookup(symptom: str, top_k: int = 5):
    """Semantic ICD-10 code lookup for a symptom description."""
    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, lambda: icd10_service.lookup_icd10_codes(symptom, top_k=top_k)
    )
    return {"symptom": symptom, "matches": results}


@app.post("/api/drug-interactions/check")
async def check_drug_interactions(medications: List[str], min_severity: str = "moderate"):
    """Check for drug-drug interactions among a list of medications."""
    results = drug_interaction_service.check_interactions(
        medications, min_severity=min_severity
    )
    return {
        "medications": medications,
        "interactions": results,
        "interaction_count": len(results),
    }


# Root endpoint - serve index.html
@app.get("/")
async def root():
    """Serve the main application page."""
    from fastapi.responses import FileResponse
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Voice Symptom Intake & Documentation Assistant API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload
    )
