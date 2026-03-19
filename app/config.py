"""Application configuration using Pydantic settings."""

from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
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

    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
