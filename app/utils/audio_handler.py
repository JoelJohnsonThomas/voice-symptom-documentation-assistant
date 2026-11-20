"""
Audio Handler Utilities

Handles audio file upload, validation, and preprocessing.
"""

import io
import os
import librosa
import soundfile as sf
import numpy as np
from pathlib import Path
from typing import Tuple, BinaryIO
import logging
import tempfile
import subprocess
import shutil

from app.config import settings

logger = logging.getLogger(__name__)


class AudioHandler:
    """Handler for audio file operations."""
    
    SUPPORTED_FORMATS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg', '.webm']
    
    @staticmethod
    def validate_audio_file(file_path: str) -> bool:
        """
        Validate audio file format and existence.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            True if valid, False otherwise
        """
        path = Path(file_path)
        
        if not path.exists():
            logger.error(f"Audio file not found: {file_path}")
            return False
        
        if path.suffix.lower() not in AudioHandler.SUPPORTED_FORMATS:
            logger.error(f"Unsupported audio format: {path.suffix}")
            return False
        
        return True
    
    @staticmethod
    def convert_webm_to_wav(input_path: str) -> str:
        """
        Convert WebM to WAV using FFmpeg.
        
        Args:
            input_path: Path to WebM file
            
        Returns:
            Path to converted WAV file
        """
        # Check if ffmpeg is available
        ffmpeg_path = shutil.which('ffmpeg') or '/opt/homebrew/bin/ffmpeg'
        if not os.path.isfile(ffmpeg_path):
            raise RuntimeError("FFmpeg not found. Please install FFmpeg for WebM support.")
        
        # Create temp WAV file
        output_path = input_path.replace('.webm', '.wav')
        if output_path == input_path:
            output_path = input_path + '.wav'
        
        logger.info(f"Converting WebM to WAV: {input_path} -> {output_path}")
        
        try:
            result = subprocess.run([
                ffmpeg_path, '-y', '-i', input_path,
                '-acodec', 'pcm_s16le',
                '-ar', str(settings.audio_sample_rate),
                '-ac', '1',  # Mono
                output_path
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                raise RuntimeError(f"FFmpeg conversion failed: {result.stderr}")
            
            logger.info("WebM to WAV conversion successful")
            return output_path
            
        except subprocess.TimeoutExpired:
            raise RuntimeError("FFmpeg conversion timed out")
        except Exception as e:
            logger.error(f"Conversion failed: {e}")
            raise
    
    @staticmethod
    def load_audio(
        file_path: str = None,
        file_bytes: bytes = None,
        target_sr: int = None
    ) -> Tuple[np.ndarray, int]:
        """
        Load audio file and convert to target sample rate.
        
        Args:
            file_path: Path to audio file
            file_bytes: Audio file bytes (alternative to file_path)
            target_sr: Target sample rate (default from settings)
            
        Returns:
            Tuple of (audio_array, sample_rate)
        """
        if target_sr is None:
            target_sr = settings.audio_sample_rate
        
        converted_path = None
        
        try:
            if file_path:
                logger.info(f"Loading audio from file: {file_path}")
                
                # Handle WebM format by converting to WAV first
                if file_path.lower().endswith('.webm'):
                    converted_path = AudioHandler.convert_webm_to_wav(file_path)
                    audio, sr = sf.read(converted_path, dtype='float32')
                else:
                    # Use soundfile for standard formats
                    audio, sr = sf.read(file_path, dtype='float32')
                
            elif file_bytes:
                logger.info("Loading audio from bytes")
                audio_io = io.BytesIO(file_bytes)
                audio, sr = sf.read(audio_io, dtype='float32')
            else:
                raise ValueError("Either file_path or file_bytes must be provided")
            
            # Convert stereo to mono if needed
            if audio.ndim > 1:
                audio = audio.mean(axis=1)
            
            # Resample if needed
            if sr != target_sr:
                logger.info(f"Resampling from {sr}Hz to {target_sr}Hz")
                audio = librosa.resample(audio, orig_sr=sr, target_sr=target_sr)
                sr = target_sr
            
            # Validate audio is not empty
            if audio is None or len(audio) == 0:
                raise RuntimeError("Loaded audio is empty")
            
            duration = len(audio) / sr
            logger.info(f"Audio loaded: {duration:.2f}s duration, {sr}Hz sample rate")
            
            # Validate duration
            if duration > settings.max_audio_duration_seconds:
                raise ValueError(
                    f"Audio duration ({duration:.1f}s) exceeds maximum "
                    f"({settings.max_audio_duration_seconds}s)"
                )
            
            if duration < 0.5:
                raise ValueError(f"Audio too short ({duration:.1f}s), minimum 0.5s required")
            
            return audio, sr
            
        except Exception as e:
            logger.error(f"Failed to load audio: {e}")
            raise
        finally:
            # Cleanup converted file
            if converted_path and Path(converted_path).exists():
                try:
                    Path(converted_path).unlink()
                except:
                    pass
    
    @staticmethod
    def save_audio(audio: np.ndarray, sr: int, output_path: str):
        """
        Save audio array to file.
        
        Args:
            audio: Audio array
            sr: Sample rate
            output_path: Output file path
        """
        try:
            sf.write(output_path, audio, sr)
            logger.info(f"Audio saved to: {output_path}")
        except Exception as e:
            logger.error(f"Failed to save audio: {e}")
            raise
    
    @staticmethod
    def get_audio_info(file_path: str) -> dict:
        """
        Get audio file information without loading full file.
        
        Args:
            file_path: Path to audio file
            
        Returns:
            Dictionary with audio metadata
        """
        try:
            info = sf.info(file_path)
            return {
                "duration": info.duration,
                "sample_rate": info.samplerate,
                "channels": info.channels,
                "format": info.format,
                "subtype": info.subtype
            }
        except Exception as e:
            logger.error(f"Failed to get audio info: {e}")
            raise
