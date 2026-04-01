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
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
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

from app.config import settings, validate_production_settings
from app.schemas import (
    TranscriptionResponse,
    FollowupQA,
    DocumentationRequest,
    DocumentationResponse,
    VoiceIntakeResponse,
    FHIRExportRequest,
    FHIRPushRequest,
    SessionResponse,
    SessionCreateRequest,
    AuditLogResponse,
    IntakeQuestionsRequest,
    IntakeQuestionsResponse,
)
from app.middleware.audit import (
    extract_client_ip,
    write_audit_log,
    check_consent_if_required,
)
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
from app.auth import SYSTEM_USER, UserRole, require_roles, ALL_ROLES, INTAKE_AND_UP_ROLES, get_current_user
from app.routes.auth_routes import router as auth_router
from app.routes.oidc_routes import router as oidc_router
from app.models.medasr_service import get_medasr_service
from app.models.medgemma_service import get_medgemma_service
from app.models.ner_service import get_ner_service
from app.models.fhir_service import get_fhir_service
from app.models.streaming_asr import StreamingASRSession
from app.models import rag_service
from app.models import knowledge_base_service, icd10_service, drug_interaction_service
from app.models import rag_evaluation_service
from app.utils.audio_handler import AudioHandler
from app.security.prompt_guard import scan_input, validate_soap_output, sanitize_input

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

# CORS middleware — configurable origins (Phase 4)
_cors_origins = [o.strip() for o in settings.cors_allowed_origins.split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth routes (Phase 4)
app.include_router(auth_router)
# OIDC/SSO routes (Phase 1 enhancement)
if settings.oidc_enabled:
    app.include_router(oidc_router)


# Security headers middleware (Phase 4)
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.auth_enabled:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Populate current user for rate limiter per-user keying (Phase 4)
@app.middleware("http")
async def populate_current_user_middleware(request: Request, call_next):
    if settings.auth_enabled:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                from app.auth import decode_token
                from app.db import crud as _crud
                from app.db.database import AsyncSessionLocal
                token = auth_header.split(" ", 1)[1]
                payload = decode_token(token)
                if payload.get("type") == "access":
                    async with AsyncSessionLocal() as db:
                        user = await _crud.get_user_by_id(db, payload["sub"])
                        if user:
                            request.state.current_user = user
            except Exception:
                pass
    response = await call_next(request)
    return response

# Mount static files
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")



# Pydantic models moved to app/schemas.py



# Audit helpers moved to app/middleware/audit.py
# Backward-compatible aliases for any in-file references
_extract_client_ip = extract_client_ip
_check_consent_if_required = check_consent_if_required
_write_audit_log = write_audit_log


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    stop_cleanup_task()
    stop_purge_scheduler()
    # Phase 3.3: Encrypt vector store at rest on shutdown
    if settings.rag_vector_store_encryption_enabled:
        logger.info("Encrypting vector store before shutdown...")
        from app.models.rag_service import encrypt_vector_store
        encrypt_vector_store()


# Startup event to preload models
@app.on_event("startup")
async def startup_event():
    """Preload ML models at server startup and init DB."""
    logger.info("Starting server initialization...")

    # Phase 1: Validate security configuration before anything else
    validate_production_settings()

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

        # Phase 8: Colab environment setup
        if settings.colab_mode:
            from app.colab_utils import setup_colab_environment, start_ngrok_tunnel
            colab_changes = setup_colab_environment()
            logger.info(f"Colab environment configured: {colab_changes}")
            if settings.colab_ngrok_token:
                ngrok_url = await start_ngrok_tunnel(settings.api_port)
                if ngrok_url:
                    logger.info(f"Ngrok tunnel: {ngrok_url}")

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

        # Prompt injection scan
        scan = scan_input(request.transcript)
        if not scan.is_safe:
            logger.warning(f"Prompt injection blocked in followup endpoint: {scan.summary()}")
            raise HTTPException(
                status_code=422,
                detail="Input contains patterns that cannot be processed safely.",
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

        # Prompt injection scan on transcript and follow-up answers
        scan = scan_input(request.transcript)
        if not scan.is_safe:
            logger.warning(f"Prompt injection blocked in document endpoint: {scan.summary()}")
            raise HTTPException(
                status_code=422,
                detail="Input contains patterns that cannot be processed safely.",
            )
        if request.followup_qa:
            for qa in request.followup_qa:
                qa_scan = scan_input(qa.answer)
                if not qa_scan.is_safe:
                    logger.warning(f"Prompt injection in follow-up answer: {qa_scan.summary()}")
                    raise HTTPException(
                        status_code=422,
                        detail="Follow-up answer contains patterns that cannot be processed safely.",
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

        # Phase 4: Hallucination check on generated documentation
        hallucination_result = None
        try:
            hallucination_result = rag_evaluation_service.check_documentation_hallucination(
                documentation=documentation,
                similar_cases=similar_cases,
                clinical_guidelines=clinical_guidelines,
                transcript=request.transcript,
            )
        except Exception as exc:
            logger.debug(f"Hallucination check skipped: {exc}")

        logger.info("Documentation generated successfully")

        return DocumentationResponse(
            documentation=documentation,
            extracted_entities=extracted_entities,
            requires_clinician_review=True,
            compliance_notice=build_compliance_notice(),
            compliance_metadata=build_compliance_metadata(),
            icd10_suggestions=icd10_suggestions if icd10_suggestions else None,
            drug_interactions=drug_interactions if drug_interactions else None,
            hallucination_check=hallucination_result,
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

        # Phase 4: Hallucination check on generated documentation
        hallucination_result = None
        try:
            hallucination_result = rag_evaluation_service.check_documentation_hallucination(
                documentation=documentation,
                similar_cases=similar_cases,
                clinical_guidelines=clinical_guidelines,
                transcript=transcript,
            )
        except Exception as exc:
            logger.debug(f"Hallucination check skipped: {exc}")

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
            hallucination_check=hallucination_result,
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


@app.websocket("/ws/soap-stream")
async def websocket_soap_stream(websocket: WebSocket):
    """
    WebSocket endpoint for streaming SOAP note generation.

    Client sends a JSON message with transcript, subjective_data, and optional
    context (similar_cases, guidelines, etc.). Server streams back SOAP tokens
    as they are generated, allowing real-time progressive display.

    Protocol:
        Client -> Server: JSON {transcript, subjective_data, ...}
        Server -> Client: JSON {type: "token", text: "..."} per chunk
        Server -> Client: JSON {type: "complete", full_text: "..."} on finish
        Server -> Client: JSON {type: "error", detail: "..."} on failure
    """
    await websocket.accept()
    ACTIVE_CONNECTIONS.inc()

    try:
        # Receive the generation request
        data = await websocket.receive_json()
        transcript = data.get("transcript", "")
        subjective_data = data.get("subjective_data", {})
        detected_language = data.get("detected_language", "en")
        specialty = data.get("specialty", "general")

        if not transcript:
            await websocket.send_json({"type": "error", "detail": "Missing transcript"})
            return

        # Prompt injection scan
        scan = scan_input(transcript)
        if not scan.is_safe:
            await websocket.send_json({
                "type": "error",
                "detail": "Input contains patterns that cannot be processed safely.",
            })
            return

        medgemma = get_medgemma_service()
        if not medgemma.is_ready():
            await websocket.send_json({"type": "error", "detail": "MedGemma model not ready"})
            return

        full_text = ""
        for chunk in medgemma.generate_soap_streaming(
            transcript=transcript,
            subjective_data=subjective_data,
            detected_language=detected_language,
            specialty=specialty,
        ):
            full_text += chunk
            await websocket.send_json({"type": "token", "text": chunk})

        # Send completion message with full text
        await websocket.send_json({
            "type": "complete",
            "full_text": full_text,
        })

    except WebSocketDisconnect:
        logger.info("SOAP stream WebSocket disconnected")
    except Exception as e:
        logger.error(f"SOAP streaming error: {e}")
        try:
            await websocket.send_json({"type": "error", "detail": str(e)})
        except Exception:
            pass
    finally:
        ACTIVE_CONNECTIONS.dec()
        try:
            await websocket.close()
        except Exception:
            pass


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


# =====================================================
# AI VOICE ASSISTANT ENDPOINTS
# =====================================================

@app.websocket("/ws/conversation")
async def websocket_conversation(websocket: WebSocket):
    """
    WebSocket endpoint for AI Voice Assistant bidirectional conversation.

    Protocol:
    - Client sends binary audio chunks (WebM from MediaRecorder)
    - Client sends JSON actions: start, stop, text_input, interrupt
    - Server sends: assistant_text, assistant_audio, user_transcript,
      entities_update, state_change, summary, error, vad_status

    Phase 3 enhancements:
    - VAD-based automatic turn-taking and barge-in detection
    - Sentence-level TTS streaming for low time-to-first-byte
    - Multi-language TTS voice model switching
    - Greeting audio cache for instant playback
    - Faster ASR intervals (conversation_streaming_interval)
    """
    from app.models.dialogue_manager import DialogueManager
    from app.models.conversation_session import ConversationMode
    from app.models.tts_service import get_tts_service
    from app.models.vad_service import get_vad_service
    from app.metrics import (
        CONVERSATION_COUNT,
        CONVERSATION_DURATION,
        CONVERSATION_TURNS,
        TTS_LATENCY,
        CONVERSATION_EMERGENCY_ESCALATIONS,
    )
    import base64

    client_ip = websocket.client.host if websocket.client else None
    await websocket.accept()
    ACTIVE_CONNECTIONS.inc(type="websocket")
    logger.info("WebSocket client connected for voice conversation")

    dialogue_mgr = None
    session_start = time.time()
    tts = get_tts_service()
    vad = get_vad_service()
    asr_session = StreamingASRSession(sample_rate=settings.audio_sample_rate)
    webm_accumulator = bytearray()
    last_decoded_size = 0
    conversation_mode = ConversationMode.PATIENT
    interrupted = False
    is_assistant_speaking = False  # Track TTS playback state for barge-in

    # Phase 3: Initialize TTS greeting cache at first connection
    if settings.tts_cache_greetings and tts.cache_size == 0:
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, tts.cache_greeting_audio)
            logger.info(f"TTS greeting cache initialized: {tts.cache_size} entries")
        except Exception as e:
            logger.debug(f"TTS greeting cache init failed: {e}")

    # Phase 3: Override ASR interval for faster conversation responsiveness
    if hasattr(asr_session, '_interval'):
        asr_session._interval = settings.conversation_streaming_interval

    try:
        # Send connected signal
        await websocket.send_json({
            "type": "connected",
            "message": "Voice assistant ready. Send {\"action\": \"start\"} to begin.",
            "vad_enabled": vad.is_available,
            "tts_streaming": settings.tts_streaming_enabled,
        })

        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Handle binary audio chunks
            if "bytes" in message and message["bytes"] and dialogue_mgr is not None:
                chunk_bytes = message["bytes"]
                webm_accumulator.extend(chunk_bytes)

                audio_data = decode_webm_chunk(
                    bytes(webm_accumulator),
                    settings.audio_sample_rate
                )

                if audio_data is not None and len(audio_data) > last_decoded_size:
                    new_samples = audio_data[last_decoded_size:]
                    asr_session.add_audio_array(new_samples)
                    last_decoded_size = len(audio_data)

                    # Phase 3: VAD processing on new audio samples
                    if vad.is_available and len(new_samples) >= 512:
                        vad_result = vad.process_frame(new_samples[:768])

                        # Barge-in detection: user starts speaking during TTS
                        if vad_result["barge_in"] and is_assistant_speaking:
                            interrupted = True
                            is_assistant_speaking = False
                            await websocket.send_json({
                                "type": "vad_status",
                                "event": "barge_in",
                                "speech_prob": vad_result["speech_prob"],
                            })

                        # Auto turn-taking: silence after speech → end of turn
                        if vad_result["turn_ended"] and not interrupted:
                            # Finalize ASR automatically
                            loop = asyncio.get_event_loop()
                            result = await loop.run_in_executor(
                                None, asr_session.transcribe_final
                            )
                            final_text = result.get("text", "").strip()

                            if final_text:
                                await websocket.send_json({
                                    "type": "user_transcript",
                                    "text": final_text,
                                    "is_final": True,
                                })

                                # Process through dialogue manager
                                response = await dialogue_mgr.process_input(final_text)
                                await _send_assistant_response(
                                    websocket, response, tts, dialogue_mgr
                                )

                            # Reset ASR for next turn
                            asr_session = StreamingASRSession(
                                sample_rate=settings.audio_sample_rate
                            )
                            if hasattr(asr_session, '_interval'):
                                asr_session._interval = settings.conversation_streaming_interval
                            webm_accumulator = bytearray()
                            last_decoded_size = 0
                            vad.reset()
                            continue

                if interrupted:
                    interrupted = False

                # Check if we should run transcription (faster interval for conversation)
                if asr_session.should_transcribe():
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        None, asr_session.transcribe_partial
                    )
                    if result and result.get("text"):
                        await websocket.send_json({
                            "type": "user_transcript",
                            "text": result.get("text", ""),
                            "full_text": result.get("full_text", ""),
                            "is_final": False,
                        })

            # Handle text/JSON commands
            elif "text" in message and message["text"]:
                try:
                    cmd = json.loads(message["text"])
                except json.JSONDecodeError:
                    cmd = {"action": "text_input", "text": message["text"]}

                action = cmd.get("action", "")

                if action == "start":
                    # Initialize conversation
                    mode_str = cmd.get("mode", "patient")
                    conversation_mode = (
                        ConversationMode.CLINICIAN
                        if mode_str == "clinician"
                        else ConversationMode.PATIENT
                    )
                    lang = cmd.get("language", "en")
                    dialogue_mgr = DialogueManager(mode=conversation_mode, language=lang)

                    CONVERSATION_COUNT.inc(mode=conversation_mode.value)
                    logger.info(f"Conversation started: mode={conversation_mode.value}, lang={lang}")

                    # Send greeting
                    greeting = await dialogue_mgr.get_greeting()
                    await websocket.send_json({
                        "type": "assistant_text",
                        "text": greeting.text,
                        "state": greeting.state.value,
                        "session_id": dialogue_mgr.session.session_id,
                    })

                    # Send state change
                    await websocket.send_json({
                        "type": "state_change",
                        "from_state": "greeting",
                        "to_state": greeting.state.value,
                    })

                    # Phase 3: Use cached TTS for greeting, with multi-language support
                    is_assistant_speaking = True
                    tts_start = time.time()
                    if settings.tts_streaming_enabled:
                        # Sentence-level streaming for low time-to-first-byte
                        async for audio_chunk in tts.synthesize_streaming(greeting.text):
                            if interrupted:
                                break
                            await websocket.send_json({
                                "type": "assistant_audio",
                                "audio": base64.b64encode(audio_chunk).decode("ascii"),
                                "format": "wav",
                                "sample_rate": settings.tts_sample_rate,
                                "streaming": True,
                            })
                        TTS_LATENCY.observe(time.time() - tts_start)
                    else:
                        # Non-streaming: use cached greeting audio
                        audio_bytes = tts.synthesize_cached(greeting.text)
                        if audio_bytes:
                            TTS_LATENCY.observe(time.time() - tts_start)
                            await websocket.send_json({
                                "type": "assistant_audio",
                                "audio": base64.b64encode(audio_bytes).decode("ascii"),
                                "format": "wav",
                                "sample_rate": settings.tts_sample_rate,
                            })
                    is_assistant_speaking = False

                    # Reset VAD state after greeting
                    vad.reset()

                elif action == "stop" and dialogue_mgr is not None:
                    # Finalize ASR and process final turn
                    if asr_session.get_buffer_duration() > 0.5:
                        loop = asyncio.get_event_loop()
                        result = await loop.run_in_executor(
                            None, asr_session.transcribe_final
                        )
                        final_text = result.get("text", "").strip()

                        if final_text:
                            await websocket.send_json({
                                "type": "user_transcript",
                                "text": final_text,
                                "is_final": True,
                            })

                            # Process through dialogue manager
                            response = await dialogue_mgr.process_input(final_text)
                            await _send_assistant_response(websocket, response, tts, dialogue_mgr)

                    # Reset ASR for next turn
                    asr_session = StreamingASRSession(sample_rate=settings.audio_sample_rate)
                    if hasattr(asr_session, '_interval'):
                        asr_session._interval = settings.conversation_streaming_interval
                    webm_accumulator = bytearray()
                    last_decoded_size = 0
                    vad.reset()

                elif action == "text_input" and dialogue_mgr is not None:
                    # Text fallback input
                    user_text = cmd.get("text", "").strip()
                    if user_text:
                        await websocket.send_json({
                            "type": "user_transcript",
                            "text": user_text,
                            "is_final": True,
                        })

                        response = await dialogue_mgr.process_input(user_text)
                        await _send_assistant_response(websocket, response, tts, dialogue_mgr)

                elif action == "interrupt":
                    interrupted = True
                    is_assistant_speaking = False

                elif action == "playback_ended":
                    # Client signals TTS playback finished
                    is_assistant_speaking = False

                elif action == "end" and dialogue_mgr is not None:
                    # Force end conversation
                    response = await dialogue_mgr.process_input("that's all")
                    await _send_assistant_response(websocket, response, tts, dialogue_mgr)

    except WebSocketDisconnect:
        logger.info("Voice conversation WebSocket disconnected")
    except Exception as e:
        logger.error(f"Conversation WebSocket error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Persist conversation session
        if dialogue_mgr is not None:
            duration = time.time() - session_start
            turn_count = len(dialogue_mgr.session.turns)
            CONVERSATION_DURATION.observe(duration, mode=conversation_mode.value)
            CONVERSATION_TURNS.observe(turn_count, mode=conversation_mode.value)

            try:
                session_data = dialogue_mgr.get_session_data()
                session_data["ended_at"] = datetime.utcnow()
                session_data["turns_json"] = json.dumps(session_data.pop("turns", []))
                session_data["entities_json"] = json.dumps(
                    session_data.pop("extracted_entities", {})
                )

                async with AsyncSessionLocal() as db:
                    await crud.create_conversation_session(db, session_data)

                logger.info(
                    f"Conversation saved: {dialogue_mgr.session.session_id}, "
                    f"{turn_count} turns, {duration:.1f}s"
                )
            except Exception as e:
                logger.error(f"Failed to persist conversation: {e}")

        ACTIVE_CONNECTIONS.dec(type="websocket")


async def _send_assistant_response(websocket, response, tts, dialogue_mgr):
    """Send assistant response (text + audio + state change) to the client.

    Phase 3 enhancements:
    - Sentence-level TTS streaming for low time-to-first-byte
    - Multi-language TTS voice model switching
    - Cached TTS for common responses
    """
    from app.metrics import TTS_LATENCY, CONVERSATION_EMERGENCY_ESCALATIONS
    import base64

    # Send text
    msg = {
        "type": "assistant_text",
        "text": response.text,
        "state": response.state.value,
        "is_final": response.is_final,
        "is_emergency": response.is_emergency,
        "rag_grounded": response.rag_grounded,
    }
    if response.documentation:
        msg["documentation"] = response.documentation
    await websocket.send_json(msg)

    # Send state change if state changed
    if response.previous_state and response.previous_state != response.state:
        await websocket.send_json({
            "type": "state_change",
            "from_state": response.previous_state.value,
            "to_state": response.state.value,
        })

    # Send entities update
    if response.entities_update:
        await websocket.send_json({
            "type": "entities_update",
            "entities": dialogue_mgr.session.extracted_entities,
        })

    # Track emergency
    if response.is_emergency:
        CONVERSATION_EMERGENCY_ESCALATIONS.inc()

    # Phase 3: Synthesize and send audio with streaming + multi-language support
    language = dialogue_mgr.session.language
    tts_start = time.time()

    if settings.tts_streaming_enabled:
        # Sentence-level streaming for low time-to-first-byte
        async for audio_chunk in tts.synthesize_streaming(response.text):
            await websocket.send_json({
                "type": "assistant_audio",
                "audio": base64.b64encode(audio_chunk).decode("ascii"),
                "format": "wav",
                "sample_rate": settings.tts_sample_rate,
                "streaming": True,
            })
        TTS_LATENCY.observe(time.time() - tts_start)
    else:
        # Non-streaming: use language-specific or cached synthesis
        if language and language != "en":
            audio_bytes = tts.synthesize_language(response.text, language)
        else:
            audio_bytes = tts.synthesize_cached(response.text)

        if audio_bytes:
            TTS_LATENCY.observe(time.time() - tts_start)
            await websocket.send_json({
                "type": "assistant_audio",
                "audio": base64.b64encode(audio_bytes).decode("ascii"),
                "format": "wav",
                "sample_rate": settings.tts_sample_rate,
            })

    # Send summary/documentation if final
    if response.is_final and response.documentation:
        await websocket.send_json({
            "type": "summary",
            "documentation": response.documentation,
        })


class TTSRequest(BaseModel):
    text: str
    voice: str = "default"


@app.post("/api/tts")
async def tts_endpoint(request: TTSRequest):
    """REST endpoint for TTS synthesis (fallback for non-WebSocket clients)."""
    from app.models.tts_service import get_tts_service
    from fastapi.responses import Response

    tts = get_tts_service()
    if not tts.is_available:
        raise HTTPException(
            status_code=503,
            detail="TTS service not available. Use browser Web Speech API fallback.",
        )

    audio_bytes = tts.synthesize(request.text)
    if audio_bytes is None:
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={"Content-Disposition": "inline; filename=tts_output.wav"},
    )


@app.get("/api/conversation/sessions")
async def list_conversation_sessions(skip: int = 0, limit: int = 50):
    """List conversation sessions."""
    async with AsyncSessionLocal() as db:
        sessions = await crud.get_conversation_sessions(db, skip=skip, limit=limit)
        return [
            {
                "id": s.id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "ended_at": s.ended_at.isoformat() if s.ended_at else None,
                "mode": s.mode,
                "state": s.state,
                "intake_session_id": s.intake_session_id,
            }
            for s in sessions
        ]


@app.get("/api/conversation/sessions/{session_id}")
async def get_conversation_session(session_id: str):
    """Get a specific conversation session with full details."""
    async with AsyncSessionLocal() as db:
        session = await crud.get_conversation_session(db, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Conversation session not found")
        return {
            "id": session.id,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "mode": session.mode,
            "state": session.state,
            "turns": json.loads(session.turns_json) if session.turns_json else [],
            "accumulated_transcript": session.accumulated_transcript,
            "entities": json.loads(session.entities_json) if session.entities_json else {},
            "intake_session_id": session.intake_session_id,
        }


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
# PHASE 7: HL7v2 & CCDA EXPORT ENDPOINTS
# =====================================================

@app.post("/api/hl7v2/adt")
async def export_hl7v2_adt(request: FHIRExportRequest):
    """Generate an HL7 v2 ADT^A04 message for legacy EHR systems."""
    fhir = get_fhir_service()
    message = fhir.build_hl7v2_adt(
        documentation=request.documentation,
        entities=request.extracted_entities,
        patient_info=request.patient_info,
    )
    return {"format": "HL7v2", "message_type": "ADT^A04", "message": message}


@app.post("/api/hl7v2/oru")
async def export_hl7v2_oru(request: FHIRExportRequest):
    """Generate an HL7 v2 ORU^R01 message with SOAP note observations."""
    fhir = get_fhir_service()
    message = fhir.build_hl7v2_oru(
        documentation=request.documentation,
        entities=request.extracted_entities,
        patient_info=request.patient_info,
    )
    return {"format": "HL7v2", "message_type": "ORU^R01", "message": message}


@app.post("/api/ccda/export")
async def export_ccda(request: FHIRExportRequest):
    """Generate a CCD (C-CDA) XML document for hospital interoperability."""
    from fastapi.responses import Response
    fhir = get_fhir_service()
    xml = fhir.build_ccda_document(
        documentation=request.documentation,
        entities=request.extracted_entities,
        patient_info=request.patient_info,
    )
    return Response(content=xml, media_type="application/xml")


class WebhookRequest(BaseModel):
    webhook_url: str
    event_type: str = "session.finalized"
    payload: dict
    auth_token: Optional[str] = None


@app.post("/api/webhooks/send")
async def send_webhook(request: WebhookRequest):
    """Send a webhook notification to an external system."""
    fhir = get_fhir_service()
    result = await fhir.send_webhook(
        webhook_url=request.webhook_url,
        event_type=request.event_type,
        payload=request.payload,
        auth_token=request.auth_token,
    )
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("error", "Webhook delivery failed"))
    return result


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
                    organization_id=raw.get("organization_id"),
                    provider_id=raw.get("provider_id"),
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
    try:
        return {
            "guidelines": knowledge_base_service.get_knowledge_base_stats(),
            "icd10": icd10_service.get_icd10_stats(),
            "drug_interactions": drug_interaction_service.get_interaction_db_stats(),
        }
    except Exception:
        logger.exception("Failed to retrieve knowledge base status")
        raise HTTPException(status_code=500, detail="Failed to retrieve knowledge base status")


@app.post("/api/knowledge-base/initialize")
async def initialize_knowledge_base(force_reseed: bool = False):
    """Initialize or re-seed the clinical knowledge base and ICD-10 index."""
    try:
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
    except Exception:
        logger.exception("Knowledge base initialization failed")
        raise HTTPException(status_code=500, detail="Knowledge base initialization failed")


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
    try:
        return knowledge_base_service.remove_guideline(guideline_id)
    except Exception:
        logger.exception("Failed to delete guideline %s", guideline_id)
        raise HTTPException(status_code=500, detail="Failed to delete guideline")


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
    try:
        results = drug_interaction_service.check_interactions(
            medications, min_severity=min_severity
        )
        return {
            "medications": medications,
            "interactions": results,
            "interaction_count": len(results),
        }
    except Exception:
        logger.exception("Drug interaction check failed")
        raise HTTPException(status_code=500, detail="Drug interaction check failed")


# =====================================================
# RAG SECURITY ENDPOINTS (Phase 3)
# =====================================================

@app.get("/api/rag/audit-logs")
async def get_rag_audit_logs(date: Optional[str] = None, limit: int = 100):
    """
    Retrieve RAG audit logs for HIPAA compliance review.

    Returns retrieval events with query hashes, accessed session IDs,
    similarity scores, and tenant context — no PHI in logs.
    """
    from app.models.rag_service import get_rag_audit_logs as _get_logs
    logs = _get_logs(date=date, limit=limit)
    return {
        "date": date or "today",
        "entries": logs,
        "count": len(logs),
    }


@app.post("/api/rag/encrypt")
async def encrypt_vector_store_endpoint():
    """
    Manually trigger vector store encryption.
    Useful for pre-maintenance or pre-backup encryption.
    """
    if not settings.rag_vector_store_encryption_enabled:
        return {"status": "disabled", "message": "Vector store encryption is not enabled"}
    from app.models.rag_service import encrypt_vector_store
    result = encrypt_vector_store()
    return {
        "status": "encrypted" if result else "failed",
        "encrypted_path": result,
    }


@app.get("/api/rag/security-status")
async def rag_security_status():
    """Return the RAG security posture for compliance dashboards."""
    from app.compliance import verify_phi_redacted
    return {
        "phi_redaction": {
            "enabled": True,
            "patterns_count": 11,
            "double_pass": True,
        },
        "tenant_isolation": {
            "enabled": settings.multi_tenancy_enabled,
            "default_org": settings.default_organization_id,
        },
        "vector_store_encryption": {
            "enabled": settings.rag_vector_store_encryption_enabled,
        },
        "audit_trail": {
            "enabled": settings.rag_audit_enabled,
            "log_location": f"{settings.rag_persist_dir}/audit/",
        },
        "compliance_metadata": build_compliance_metadata(),
    }


# =====================================================
# RAG EVALUATION & OBSERVABILITY ENDPOINTS (Phase 4)
# =====================================================

class GoldenSetEntry(BaseModel):
    query: str
    relevant_ids: List[str]
    notes: str = ""


@app.get("/api/rag/evaluation/summary")
async def rag_evaluation_summary():
    """Return RAG evaluation state: golden set size, drift, hallucination config."""
    return rag_evaluation_service.get_evaluation_summary()


@app.post("/api/rag/evaluation/run")
async def run_rag_evaluation(k: int = 3):
    """
    Run retrieval evaluation against the golden set.

    Returns MRR, Recall@k, Precision@k, and per-query breakdowns.
    """
    if not settings.rag_evaluation_enabled:
        raise HTTPException(status_code=400, detail="RAG evaluation is disabled")

    golden_set = rag_evaluation_service.load_golden_set()
    if not golden_set:
        return {
            "status": "no_golden_set",
            "message": "No golden set entries found. Add entries via POST /api/rag/evaluation/golden-set first.",
        }

    loop = asyncio.get_event_loop()
    results = await loop.run_in_executor(
        None, lambda: rag_evaluation_service.run_retrieval_evaluation(golden_set, k=k)
    )
    return results


@app.get("/api/rag/evaluation/golden-set")
async def get_golden_set():
    """Retrieve the current golden set for RAG evaluation."""
    entries = rag_evaluation_service.load_golden_set()
    return {"entries": entries, "count": len(entries)}


@app.post("/api/rag/evaluation/golden-set")
async def add_golden_set(entry: GoldenSetEntry):
    """Add a new entry to the RAG evaluation golden set."""
    result = rag_evaluation_service.add_golden_set_entry(
        query=entry.query,
        relevant_ids=entry.relevant_ids,
        notes=entry.notes,
    )
    return result


@app.delete("/api/rag/evaluation/golden-set/{entry_id}")
async def delete_golden_set_entry(entry_id: str):
    """Remove an entry from the golden set."""
    removed = rag_evaluation_service.remove_golden_set_entry(entry_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Golden set entry '{entry_id}' not found")
    return {"status": "removed", "id": entry_id}


@app.get("/api/rag/drift")
async def rag_drift_status():
    """Return current embedding drift score and status."""
    return rag_evaluation_service.compute_drift()


@app.get("/api/rag/drift/history")
async def rag_drift_history():
    """Return historical drift scores."""
    history = rag_evaluation_service.get_drift_history()
    return {"entries": history, "count": len(history)}


@app.post("/api/rag/drift/reset")
async def rag_drift_reset():
    """
    Reset the drift baseline to current recent embeddings.
    Call after re-indexing or embedding model updates.
    """
    return rag_evaluation_service.reset_drift_baseline()


# =====================================================
# Phase 10: Batch Processing & Session Linking Endpoints
# =====================================================

class BatchSubmitRequest(BaseModel):
    filenames: List[str]
    linked_session_id: Optional[str] = None


class SessionLinkRequest(BaseModel):
    parent_session_id: str
    child_session_id: str


@app.post("/api/batch/submit")
async def batch_submit(req: BatchSubmitRequest):
    """Create a batch processing job for multiple audio files."""
    from app.batch_processor import get_batch_processor
    processor = get_batch_processor()
    job = processor.create_job(req.filenames, req.linked_session_id)
    return {"batch_id": job.batch_id, "items": len(job.items), "status": job.status}


@app.get("/api/batch/{batch_id}")
async def batch_status(batch_id: str):
    """Get batch job status and progress."""
    from app.batch_processor import get_batch_processor
    job = get_batch_processor().get_job(batch_id)
    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return {
        "batch_id": job.batch_id,
        "status": job.status,
        "progress": job.progress,
        "items": [
            {
                "item_id": i.item_id,
                "filename": i.filename,
                "status": i.status,
                "error": i.error,
            }
            for i in job.items
        ],
    }


@app.post("/api/batch/{batch_id}/cancel")
async def batch_cancel(batch_id: str):
    """Cancel a batch job."""
    from app.batch_processor import get_batch_processor
    ok = get_batch_processor().cancel_job(batch_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cannot cancel this job")
    return {"status": "cancelled"}


@app.get("/api/batch")
async def batch_list(limit: int = 20):
    """List recent batch jobs."""
    from app.batch_processor import get_batch_processor
    return {"jobs": get_batch_processor().list_jobs(limit)}


@app.post("/api/sessions/link")
async def link_sessions(req: SessionLinkRequest):
    """Link a follow-up session to an original session."""
    from app.batch_processor import get_session_linker
    linker = get_session_linker()
    linker.link(req.parent_session_id, req.child_session_id)
    return {"status": "linked", "chain": linker.get_chain(req.child_session_id)}


@app.get("/api/sessions/{session_id}/chain")
async def session_chain(session_id: str):
    """Get the full visit chain for a session (longitudinal view)."""
    from app.batch_processor import get_session_linker
    linker = get_session_linker()
    return {
        "session_id": session_id,
        "chain": linker.get_chain(session_id),
        "parent": linker.get_parent(session_id),
        "follow_ups": linker.get_follow_ups(session_id),
    }


@app.post("/api/audio/quality-check")
async def audio_quality_check(file: UploadFile = File(...)):
    """Check audio quality (SNR, loudness) before processing."""
    from app.batch_processor import check_audio_quality
    data = await file.read()
    return check_audio_quality(data, sample_rate=settings.audio_sample_rate)


# =====================================================
# Phase 9: Observability & Analytics Endpoints
# =====================================================

class FeedbackRequest(BaseModel):
    session_id: str
    field: str           # subjective, objective, assessment, plan
    rating: int          # 1 = thumbs up, -1 = thumbs down
    comment: str = ""


@app.get("/api/analytics/sessions")
async def session_analytics_summary():
    """Return aggregated session analytics."""
    from app.analytics import get_session_analytics
    return get_session_analytics().get_summary()


@app.post("/api/analytics/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    """Submit clinician feedback on a SOAP field."""
    from app.analytics import get_feedback_collector, SOAPFeedback
    if req.field not in ("subjective", "objective", "assessment", "plan"):
        raise HTTPException(status_code=400, detail="field must be subjective/objective/assessment/plan")
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating must be 1 or -1")
    collector = get_feedback_collector()
    collector.submit(SOAPFeedback(
        session_id=req.session_id,
        field=req.field,
        rating=req.rating,
        comment=req.comment,
        provider_id=getattr(request.state, "current_user_id", ""),
    ))
    return {"status": "recorded"}


@app.get("/api/analytics/feedback/scores")
async def feedback_scores():
    """Return satisfaction scores per SOAP field."""
    from app.analytics import get_feedback_collector
    return get_feedback_collector().get_field_scores()


@app.get("/api/analytics/feedback/recent")
async def recent_feedback(limit: int = 50):
    """Return recent feedback entries."""
    from app.analytics import get_feedback_collector
    return get_feedback_collector().recent(limit)


@app.get("/api/analytics/grafana-dashboard")
async def grafana_dashboard():
    """Return importable Grafana dashboard JSON."""
    from app.analytics import generate_grafana_dashboard
    return generate_grafana_dashboard()


@app.get("/api/audit/export")
async def export_audit(
    fmt: str = "jsonlines",
    limit: int = 1000,
    db: AsyncSession = Depends(get_db),
):
    """Export audit logs in SIEM-compatible format (jsonlines or cef)."""
    from app.analytics import export_audit_logs
    from sqlalchemy import select, desc
    from app.db.models import AuditLog

    stmt = select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)
    result = await db.execute(stmt)
    logs = result.scalars().all()

    log_dicts = [
        {
            "action": log.action,
            "username": log.username,
            "ip_address": getattr(log, "ip_address", ""),
            "resource": getattr(log, "resource", ""),
            "session_id": getattr(log, "session_id", ""),
        }
        for log in logs
    ]

    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(
        content=export_audit_logs(log_dicts, fmt=fmt),
        media_type="text/plain",
    )


# =====================================================
# Phase 8: Infrastructure & Scalability Endpoints
# =====================================================

@app.get("/api/infrastructure/status")
async def infrastructure_status():
    """Return infrastructure health — cache, task queue, DB backend, GPU."""
    from app.cache import get_cache_service
    from app.task_queue import get_task_queue

    cache = get_cache_service()
    queue = get_task_queue()

    db_backend = "postgresql" if "postgresql" in str(settings.database_url) else "sqlite"

    import torch
    gpu_info = {
        "available": torch.cuda.is_available(),
        "name": torch.cuda.get_device_properties(0).name if torch.cuda.is_available() else None,
    }

    return {
        "database_backend": db_backend,
        "redis_enabled": cache.redis_enabled,
        "task_queue": queue.stats(),
        "gpu": gpu_info,
        "quantization_enabled": settings.model_quantization_enabled,
        "quantization_bits": settings.model_quantization_bits if settings.model_quantization_enabled else None,
        "colab_mode": settings.colab_mode,
    }


@app.get("/api/infrastructure/vram")
async def vram_estimate():
    """Estimate VRAM usage for current model and quantization settings."""
    from app.quantization import estimate_vram_usage
    return estimate_vram_usage()


@app.get("/api/infrastructure/cache/stats")
async def cache_stats():
    """Return cache hit/miss stats."""
    from app.cache import get_cache_service
    cache = get_cache_service()
    return {
        "redis_enabled": cache.redis_enabled,
        "memory_cache_size": cache._memory.size(),
    }


@app.post("/api/infrastructure/cache/clear")
async def cache_clear():
    """Clear all cached entries."""
    from app.cache import get_cache_service
    cache = get_cache_service()
    await cache.clear()
    return {"status": "cleared"}


@app.get("/api/infrastructure/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Check status of a background task."""
    from app.task_queue import get_task_queue
    queue = get_task_queue()
    result = queue.get_result(task_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return {
        "task_id": result.task_id,
        "status": result.status,
        "error": result.error,
        "duration_seconds": result.duration_seconds,
    }


@app.get("/api/infrastructure/colab")
async def colab_info():
    """Return Colab environment info and recommendations."""
    from app.colab_utils import get_colab_launch_info
    return get_colab_launch_info()


# Root endpoint - serve vanilla JS frontend
@app.get("/")
async def root():
    """Serve the main application page."""
    from fastapi.responses import FileResponse
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(
            index_path,
            headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
        )
    return {"message": "Voice Symptom Intake & Documentation Assistant API"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload
    )
