"""Model quantization utilities for reduced VRAM usage.

Phase 8: Supports 4-bit and 8-bit quantization via bitsandbytes.
Halves or quarters VRAM requirements for MedGemma models.

Set ``MODEL_QUANTIZATION_ENABLED=true`` and ``MODEL_QUANTIZATION_BITS=4``
in config or .env to enable.
"""

import logging
from typing import Any, Dict, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def get_quantization_config() -> Optional[Any]:
    """Build a BitsAndBytesConfig if quantization is enabled.

    Returns None if quantization is disabled or bitsandbytes is not installed.
    """
    if not settings.model_quantization_enabled:
        return None

    try:
        from transformers import BitsAndBytesConfig
    except ImportError:
        logger.warning("transformers BitsAndBytesConfig not available; skipping quantization")
        return None

    try:
        import bitsandbytes  # noqa: F401
    except ImportError:
        logger.warning("bitsandbytes not installed; quantization disabled")
        return None

    bits = settings.model_quantization_bits
    if bits == 4:
        config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype="bfloat16",
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
        logger.info("Quantization: 4-bit NF4 with double quantization enabled")
    elif bits == 8:
        config = BitsAndBytesConfig(
            load_in_8bit=True,
        )
        logger.info("Quantization: 8-bit enabled")
    else:
        logger.warning("Unsupported quantization bits=%d; use 4 or 8", bits)
        return None

    return config


def get_model_load_kwargs() -> Dict[str, Any]:
    """Get kwargs to pass to AutoModelForCausalLM.from_pretrained().

    Handles quantization config, device mapping, and dtype selection.
    """
    import torch

    kwargs: Dict[str, Any] = {
        "low_cpu_mem_usage": True,
        "token": settings.hf_token if settings.hf_token else None,
    }

    quant_config = get_quantization_config()

    if quant_config is not None:
        kwargs["quantization_config"] = quant_config
        kwargs["device_map"] = "auto"
        logger.info("Model will load with quantization + device_map=auto")
    elif settings.enable_gpu and torch.cuda.is_available():
        kwargs["torch_dtype"] = torch.bfloat16
        kwargs["device_map"] = "auto"
    else:
        kwargs["torch_dtype"] = torch.float32

    return kwargs


def estimate_vram_usage() -> Dict[str, Any]:
    """Estimate VRAM usage for the current quantization setting."""
    import torch

    model_name = settings.medgemma_model
    param_estimate_b = 4.0  # ~4B params for medgemma-4b

    if "27b" in model_name.lower():
        param_estimate_b = 27.0
    elif "7b" in model_name.lower():
        param_estimate_b = 7.0
    elif "2b" in model_name.lower():
        param_estimate_b = 2.0

    bits = settings.model_quantization_bits if settings.model_quantization_enabled else 16
    bytes_per_param = bits / 8
    estimated_gb = (param_estimate_b * 1e9 * bytes_per_param) / (1024 ** 3)

    gpu_available = torch.cuda.is_available()
    gpu_total_gb = 0.0
    if gpu_available:
        gpu_total_gb = torch.cuda.get_device_properties(0).total_mem / (1024 ** 3)

    return {
        "model": model_name,
        "estimated_params_billion": param_estimate_b,
        "quantization_bits": bits,
        "estimated_vram_gb": round(estimated_gb, 2),
        "gpu_available": gpu_available,
        "gpu_total_vram_gb": round(gpu_total_gb, 2),
        "fits_in_vram": gpu_total_gb >= estimated_gb if gpu_available else False,
    }
