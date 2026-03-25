"""Google Colab deployment utilities.

Phase 8: Helpers for running VoxDoc in Colab environments.
- GPU runtime auto-detection
- Ngrok tunneling for external access
- Colab-specific optimizations (memory, paths)

Set ``COLAB_MODE=true`` in config or .env to enable.
"""

import logging
import os
import sys
from typing import Dict, Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


def is_colab_environment() -> bool:
    """Detect if running inside Google Colab."""
    try:
        import google.colab  # noqa: F401
        return True
    except ImportError:
        return False


def detect_gpu_runtime() -> Dict[str, Any]:
    """Detect GPU type and available VRAM in Colab."""
    import torch

    info: Dict[str, Any] = {
        "cuda_available": torch.cuda.is_available(),
        "device_count": torch.cuda.device_count() if torch.cuda.is_available() else 0,
        "gpu_name": None,
        "vram_total_gb": 0.0,
        "vram_free_gb": 0.0,
        "recommended_quantization": None,
    }

    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        total_gb = props.total_mem / (1024 ** 3)
        free_gb = torch.cuda.mem_get_info(0)[0] / (1024 ** 3)

        info["gpu_name"] = props.name
        info["vram_total_gb"] = round(total_gb, 2)
        info["vram_free_gb"] = round(free_gb, 2)

        # Recommend quantization based on VRAM
        if total_gb < 8:
            info["recommended_quantization"] = 4
        elif total_gb < 16:
            info["recommended_quantization"] = 8
        else:
            info["recommended_quantization"] = None  # Full precision OK

    return info


def setup_colab_environment() -> Dict[str, str]:
    """Apply Colab-specific environment optimizations."""
    changes = {}

    if not settings.colab_mode:
        return changes

    # Use /content for model cache (Colab persistent storage)
    if os.path.isdir("/content"):
        model_dir = "/content/models"
        os.makedirs(model_dir, exist_ok=True)
        os.environ.setdefault("HF_HOME", "/content/hf_cache")
        changes["model_cache"] = model_dir
        changes["hf_home"] = "/content/hf_cache"

    # Reduce memory pressure
    os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "max_split_size_mb:128")
    changes["cuda_alloc_conf"] = "max_split_size_mb:128"

    # Enable TF32 for A100/T4 (faster matmul)
    import torch
    if torch.cuda.is_available():
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        changes["tf32_enabled"] = "true"

    logger.info("Colab environment configured: %s", changes)
    return changes


async def start_ngrok_tunnel(port: int = 8000) -> Optional[str]:
    """Start ngrok tunnel for external access to Colab.

    Requires ``COLAB_NGROK_TOKEN`` to be set.
    Returns the public URL or None if unavailable.
    """
    token = settings.colab_ngrok_token
    if not token:
        logger.warning("No ngrok token configured; external access unavailable")
        return None

    try:
        from pyngrok import ngrok, conf
        conf.get_default().auth_token = token
        tunnel = ngrok.connect(port, "http")
        public_url = tunnel.public_url
        logger.info("Ngrok tunnel active: %s -> localhost:%d", public_url, port)
        return public_url
    except ImportError:
        logger.warning("pyngrok not installed; run: pip install pyngrok")
        return None
    except Exception as e:
        logger.error("Failed to start ngrok tunnel: %s", e)
        return None


def get_colab_launch_info() -> Dict[str, Any]:
    """Get summary info for Colab launch display."""
    gpu_info = detect_gpu_runtime()
    return {
        "is_colab": is_colab_environment(),
        "colab_mode_enabled": settings.colab_mode,
        "gpu": gpu_info,
        "recommended_settings": {
            "enable_gpu": gpu_info["cuda_available"],
            "model_quantization_enabled": gpu_info["recommended_quantization"] is not None,
            "model_quantization_bits": gpu_info["recommended_quantization"] or 4,
            "streaming_interval_seconds": 0.5 if gpu_info["cuda_available"] else 4.0,
        },
    }
