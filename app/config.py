"""Application configuration using Pydantic settings."""

import logging
import sys

from pydantic_settings import BaseSettings
from typing import Literal

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Deployment Mode: "development" or "production"
    # In production mode, security features are enforced and insecure defaults are rejected.
    deployment_mode: Literal["development", "production"] = "development"

    # Hugging Face
    hf_token: str = ""
    
    # Models
    model_cache_dir: str = "/app/models"
    medasr_model: str = "google/medasr"
    medgemma_model: str = "google/medgemma-1.5-4b-it"
    medgemma_vision_model: str = "google/medgemma-4b-it"
    whisper_model: str = "openai/whisper-small"
    multilingual_asr_enabled: bool = True
    
    # Image Analysis
    enable_image_analysis: bool = True
    max_image_size_mb: int = 10
    
    # Device
    device: Literal["cuda", "cpu"] = "cpu"
    enable_gpu: bool = False
    
    # MedGemma Generation Parameters
    medgemma_max_tokens: int = 1024  # Sufficient for complete documentation
    medgemma_repetition_penalty: float = 1.1  # Prevent repetitive output

    # Compliance Controls
    allow_phi_logging: bool = False
    enable_phi_persistence: bool = False
    medgemma_terms_acknowledged: bool = False
    enforce_medgemma_terms_acknowledgement: bool = True

    # Audit Logging
    audit_logging_enabled: bool = False
    
    # Audio
    max_audio_duration_seconds: int = 300
    audio_sample_rate: int = 16000
    
    # Streaming Transcription
    streaming_interval_seconds: float = 2.0  # How often to run ASR on buffer (GPU: 2s, CPU: 4s)
    
    # Rate Limiting & Queue
    rate_limiting_enabled: bool = True
    rate_limit_general_rpm: int = 60       # General endpoints: requests per minute
    rate_limit_inference_rpm: int = 10     # Inference endpoints: requests per minute
    queue_max_concurrent_inferences: int = 2  # Max parallel model inference tasks
    queue_max_size: int = 20              # Max queued requests before rejecting
    queue_timeout_seconds: float = 120.0  # Max seconds a request waits in queue
    queue_estimated_inference_seconds: float = 10.0  # Default estimate before measurements

    # HIPAA Encryption at Rest
    encryption_at_rest_enabled: bool = False
    encryption_master_key: str = "CHANGE_ME_IN_PRODUCTION"
    encryption_kdf_iterations: int = 100000

    # Data Retention & Auto-Purge
    retention_sessions_days: int = 365       # Intake sessions retention (0 = keep forever)
    retention_audit_logs_days: int = 2555    # ~7 years (HIPAA requires min 6 years)
    auto_purge_enabled: bool = False
    auto_purge_interval_hours: int = 24      # How often auto-purge runs

    # Monitoring & Observability
    metrics_enabled: bool = True
    structured_logging_enabled: bool = True
    metrics_endpoint_auth_required: bool = False  # /metrics endpoint — set True for production
    metrics_alert_window_seconds: int = 300       # Window for alert evaluation (5 min)
    metrics_error_rate_warning: float = 0.1       # 10% error rate triggers warning
    metrics_error_rate_critical: float = 0.25     # 25% error rate triggers critical
    metrics_latency_warning_seconds: float = 15.0
    metrics_latency_critical_seconds: float = 30.0

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False

    # RAG (Retrieval-Augmented Generation)
    rag_enabled: bool = False
    rag_embedding_model: str = "NeuML/pubmedbert-base-embeddings"
    rag_persist_dir: str = "./rag_store"
    rag_top_k: int = 3
    rag_similarity_threshold: float = 0.65       # Min cosine similarity to include a result
    rag_initial_retrieval_k: int = 20            # Candidates fetched before reranking
    rag_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    rag_reranker_enabled: bool = True
    rag_chunking_enabled: bool = True            # Split SOAP into per-section chunks

    # Knowledge Base (Phase 2)
    knowledge_base_enabled: bool = False
    knowledge_base_persist_dir: str = "./knowledge_store"
    knowledge_base_guidelines_top_k: int = 3
    knowledge_base_guidelines_threshold: float = 0.60
    icd10_lookup_enabled: bool = True             # Semantic ICD-10 code matching
    icd10_top_k: int = 5                          # Max ICD-10 suggestions per symptom
    icd10_similarity_threshold: float = 0.60
    drug_interaction_check_enabled: bool = True    # Auto-check medication interactions

    # Multi-Tenancy & Isolation (Phase 3)
    multi_tenancy_enabled: bool = False
    default_organization_id: str = "default"
    default_provider_id: str = "system"

    # RAG Security (Phase 3)
    rag_audit_enabled: bool = True                # Log every RAG retrieval for HIPAA
    rag_vector_store_encryption_enabled: bool = False  # Encrypt vector store at rest

    # RAG Evaluation & Observability (Phase 4)
    rag_evaluation_enabled: bool = True
    rag_evaluation_persist_dir: str = "./rag_eval"
    rag_drift_detection_enabled: bool = True
    rag_drift_window_size: int = 50               # Embeddings to track per window
    rag_drift_threshold: float = 0.15             # Cosine distance shift triggering alert
    rag_hallucination_check_enabled: bool = True   # Cross-ref generated text vs evidence

    # Voice Assistant & Conversation
    conversation_mode_enabled: bool = False
    tts_engine: str = "piper"          # "piper" or "webspeech" (browser fallback)
    piper_model_path: str = "./models/piper/en_US-amy-medium.onnx"
    piper_config_path: str = "./models/piper/en_US-amy-medium.onnx.json"
    tts_sample_rate: int = 22050
    tts_max_text_length: int = 500
    conversation_max_turns: int = 20
    conversation_followup_rounds: int = 3
    conversation_streaming_interval: float = 0.5  # Faster ASR for conversation mode
    conversation_llm_model: str = ""  # Empty = reuse medgemma_model
    conversation_llm_separate: bool = False  # Load separate model for conversation

    # Phase 3: Voice Activity Detection
    vad_enabled: bool = True
    vad_threshold: float = 0.5         # Speech probability threshold (0-1)
    vad_min_silence_ms: int = 800      # Silence duration to trigger end-of-turn (ms)
    vad_min_speech_ms: int = 250       # Minimum speech duration to accept (ms)
    vad_window_size_ms: int = 32       # VAD analysis window (Silero uses 32ms chunks)

    # Phase 3: TTS Caching & Streaming
    tts_cache_greetings: bool = True   # Pre-cache greeting audio at startup
    tts_streaming_enabled: bool = True # Send TTS sentence-by-sentence

    # Phase 3: Multi-Language
    conversation_auto_detect_language: bool = True
    conversation_default_language: str = "en"
    piper_voice_models: str = ""       # JSON map: {"es": "./models/piper/es_ES-...", ...}

    # Phase 8: Infrastructure & Scalability
    database_url: str = ""  # Empty = use SQLite default; set to postgresql+asyncpg://... for Postgres
    redis_url: str = ""  # Empty = disabled; set to redis://localhost:6379/0
    redis_cache_ttl_seconds: int = 300  # Default cache TTL
    task_queue_enabled: bool = False  # Enable Celery/ARQ background workers
    task_queue_broker_url: str = ""  # e.g. redis://localhost:6379/1
    model_quantization_enabled: bool = False  # Enable 4-bit/8-bit quantization
    model_quantization_bits: int = 4  # 4 or 8
    colab_mode: bool = False  # Enable Colab-specific optimizations
    colab_ngrok_token: str = ""  # Ngrok auth token for Colab tunneling

    # Phase 7: EHR Integration
    webhook_enabled: bool = False
    webhook_url: str = ""  # Default webhook endpoint for session finalization
    webhook_auth_token: str = ""
    hl7v2_export_enabled: bool = True
    ccda_export_enabled: bool = True

    # Phase 5: Clinical Intelligence
    specialty_detection_enabled: bool = True
    default_specialty: str = "general"  # general, emergency, primary_care, psychiatry, ob_gyn, pediatrics
    vitals_extraction_enabled: bool = True
    differential_diagnosis_enabled: bool = True
    ambient_mode_enabled: bool = False
    diarization_enabled: bool = False
    icd10_umls_mode: str = "semantic"  # "semantic" (current) or "umls_linker" (requires scispacy linker)

    # Phase 4: Authentication & Security
    auth_enabled: bool = False                    # False = dev mode (current stub behavior)
    jwt_secret_key: str = "CHANGE_ME_IN_PRODUCTION"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    mfa_enabled: bool = False                     # TOTP MFA for provider/admin roles
    session_inactivity_timeout_minutes: int = 15  # Frontend inactivity timer
    consent_tracking_enabled: bool = True         # Require verbal consent before intake
    cors_allowed_origins: str = "*"               # Comma-separated origins; "*" for dev

    # OAuth2/OIDC SSO (Phase 1)
    oidc_enabled: bool = False                     # Enable OIDC login flow
    oidc_issuer_url: str = ""                      # e.g. https://accounts.google.com or https://login.microsoftonline.com/{tenant}/v2.0
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""                    # e.g. https://your-app.com/api/auth/oidc/callback
    oidc_scopes: str = "openid email profile"      # Space-separated scopes
    oidc_role_claim: str = "role"                   # OIDC claim that maps to UserRole
    oidc_default_role: str = "viewer"               # Default role for new OIDC users

    # Phase 4: Multi-region / Data Residency
    data_region: str = "us-east-1"                   # Deployment region for PHI locality
    allowed_data_regions: str = "us-east-1,us-west-2,eu-west-1"  # Comma-separated
    enforce_data_residency: bool = False              # Reject cross-region data transfers
    region_encryption_key_arn: str = ""               # AWS KMS ARN for region-specific encryption

    # Phase 4: vLLM Serving
    vllm_enabled: bool = False
    vllm_url: str = "http://localhost:8001"
    vllm_model: str = "google/medgemma-4b-it"

    # Phase 4: OpenTelemetry
    otel_enabled: bool = False
    otel_endpoint: str = "http://localhost:4317"

    # Phase 4: Wake Word
    picovoice_access_key: str = ""

    # Logging
    log_level: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


# ---------------------------------------------------------------------------
# Production-mode startup validation
# ---------------------------------------------------------------------------

_INSECURE_DEFAULTS = {"CHANGE_ME_IN_PRODUCTION", "", "changeme", "secret"}


def validate_production_settings() -> None:
    """Validate that security-critical settings are configured for production.

    Called during application startup. In production mode, insecure defaults
    cause a hard failure. In development mode, they emit warnings.
    """
    is_prod = settings.deployment_mode == "production"
    issues: list[str] = []

    # --- Secrets must not be default values ---
    if settings.jwt_secret_key.lower() in _INSECURE_DEFAULTS:
        issues.append(
            "JWT_SECRET_KEY is set to an insecure default. "
            "Generate a strong random secret (e.g. `openssl rand -hex 32`)."
        )

    if settings.encryption_master_key.lower() in _INSECURE_DEFAULTS:
        issues.append(
            "ENCRYPTION_MASTER_KEY is set to an insecure default. "
            "Generate a strong random secret for HIPAA encryption at rest."
        )

    # --- Production requires security features enabled ---
    if is_prod:
        if not settings.auth_enabled:
            issues.append("AUTH_ENABLED must be True in production mode.")

        if not settings.encryption_at_rest_enabled:
            issues.append("ENCRYPTION_AT_REST_ENABLED must be True in production mode.")

        if not settings.audit_logging_enabled:
            issues.append("AUDIT_LOGGING_ENABLED must be True in production mode.")

        if settings.cors_allowed_origins.strip() == "*":
            issues.append(
                "CORS_ALLOWED_ORIGINS must not be '*' in production mode. "
                "Specify allowed origins explicitly."
            )

        if not settings.metrics_endpoint_auth_required:
            issues.append(
                "METRICS_ENDPOINT_AUTH_REQUIRED should be True in production "
                "to prevent information leakage via /metrics."
            )

    # --- Report ---
    if issues:
        header = (
            "FATAL: Production security validation failed"
            if is_prod
            else "WARNING: Insecure configuration detected (development mode)"
        )
        msg = f"\n{'=' * 60}\n{header}\n{'=' * 60}\n"
        for i, issue in enumerate(issues, 1):
            msg += f"  {i}. {issue}\n"
        msg += "=" * 60

        if is_prod:
            # Hard-fail in production — do not start with insecure config
            print(msg, file=sys.stderr)
            sys.exit(1)
        else:
            logger.warning(msg)
