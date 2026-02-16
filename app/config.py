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
    
    # Device
    device: Literal["cuda", "cpu"] = "cpu"
    enable_gpu: bool = False
    
    # MedGemma Generation Parameters
    medgemma_max_tokens: int = 1024  # Sufficient for complete documentation
    medgemma_repetition_penalty: float = 1.1  # Prevent repetitive output
    
    # Audio
    max_audio_duration_seconds: int = 300
    audio_sample_rate: int = 16000
    
    # Streaming Transcription
    streaming_interval_seconds: float = 2.0  # How often to run ASR on buffer (GPU: 2s, CPU: 4s)
    
    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
