"""
MedASR Service - Medical Speech Recognition

This service uses Google's MedASR model to transcribe medical audio
with high accuracy for medical terminology.
"""

import torch
import librosa
from transformers import AutoModelForCTC, AutoProcessor, pipeline
from typing import Union, BinaryIO
import numpy as np
import logging
import whisper

from app.config import settings

logger = logging.getLogger(__name__)


class MedASRService:
    """Service for medical speech-to-text using MedASR."""
    
    def __init__(self):
        """Initialize MedASR model and processor."""
        self.device = settings.device
        self.model = None
        self.processor = None
        self.pipe = None
        self.whisper_model = None
        self._load_model()
    
    def _load_model(self):
        """Load MedASR model from Hugging Face."""
        try:
            logger.info(f"Loading MedASR model on device: {self.device}")
            
            # Use pipeline for easier inference
            self.pipe = pipeline(
                "automatic-speech-recognition",
                model=settings.medasr_model,
                device=0 if self.device == "cuda" else -1,
                token=settings.hf_token if settings.hf_token else None
            )
            
            logger.info("MedASR model loaded successfully")
            
            if getattr(settings, "multilingual_asr_enabled", False):
                logger.info(f"Loading Whisper model: {settings.whisper_model}")
                whisper_name = settings.whisper_model.split("/")[-1].replace("whisper-", "")
                self.whisper_model = whisper.load_model(whisper_name, device=self.device)
                logger.info("Whisper model loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load MedASR model: {e}")
            raise
    
    def transcribe(
        self, 
        audio_path: str = None,
        audio_array: np.ndarray = None,
        sample_rate: int = None
    ) -> tuple[str, str]:
        """
        Transcribe audio to text using MedASR.
        
        Args:
            audio_path: Path to audio file (WAV, MP3, M4A)
            audio_array: Audio array (if already loaded)
            sample_rate: Sample rate of audio_array
            
        Returns:
            Tuple of (transcribed text, detected language code)
        """
        try:
            # Load audio if path provided
            if audio_path:
                logger.info(f"Loading audio from: {audio_path}")
                audio_array, sample_rate = librosa.load(
                    audio_path, 
                    sr=settings.audio_sample_rate
                )
            elif audio_array is not None:
                # Resample if needed
                if sample_rate != settings.audio_sample_rate:
                    audio_array = librosa.resample(
                        audio_array,
                        orig_sr=sample_rate,
                        target_sr=settings.audio_sample_rate
                    )
                    sample_rate = settings.audio_sample_rate
            else:
                raise ValueError("Either audio_path or audio_array must be provided")
            
            # Check duration
            duration = len(audio_array) / sample_rate
            if duration > settings.max_audio_duration_seconds:
                raise ValueError(
                    f"Audio duration ({duration:.1f}s) exceeds maximum "
                    f"({settings.max_audio_duration_seconds}s)"
                )
            
            # Detect language if Whisper is available
            detected_language = "en"
            if self.whisper_model is not None:
                audio_float32 = audio_array.astype(np.float32)
                # Pad/trim to 30 seconds for language detection
                audio_for_detect = whisper.pad_or_trim(audio_float32)
                mel = whisper.log_mel_spectrogram(audio_for_detect, n_mels=self.whisper_model.dims.n_mels).to(self.whisper_model.device)
                _, probs = self.whisper_model.detect_language(mel)
                detected_language = max(probs, key=probs.get)
                logger.info(f"Detected language: {detected_language}")
            
            if detected_language != "en" and self.whisper_model is not None:
                logger.info(f"Transcribing {detected_language} audio ({duration:.1f}s) with Whisper...")
                result = self.whisper_model.transcribe(audio_float32, language=detected_language)
                transcript = result["text"]
            else:
                logger.info(f"Transcribing English audio ({duration:.1f}s) with MedASR...")
                
                # Transcribe using pipeline with chunking for long audio
                result = self.pipe(
                    audio_array,
                    chunk_length_s=20,  # Process in 20-second chunks
                    stride_length_s=2   # 2-second overlap between chunks
                )
                
                transcript = result["text"]
                
                # Clean up special tokens and artifacts
                import re
                transcript = re.sub(r'</?s>|<unk>|<pad>', '', transcript)  # Remove special tokens
                transcript = transcript.strip().lstrip('.,;:!? ')  # Remove leading punctuation/whitespace
                transcript = ' '.join(transcript.split())  # Normalize whitespace
            
            logger.info(f"Transcription complete: {len(transcript)} characters")
            
            return transcript, detected_language
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise
    
    def is_ready(self) -> bool:
        """Check if the model is loaded and ready."""
        return self.pipe is not None


# Global instance (singleton pattern)
_medasr_service = None


def get_medasr_service() -> MedASRService:
    """Get or create MedASR service instance."""
    global _medasr_service
    if _medasr_service is None:
        _medasr_service = MedASRService()
    return _medasr_service
