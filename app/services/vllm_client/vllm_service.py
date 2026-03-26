"""
vLLM Client — OpenAI-compatible API client for vLLM-served models.

In production, MedGemma is served via vLLM for 3-5x throughput.
This client wraps the OpenAI-compatible /v1/completions endpoint
and provides streaming + batch support.

Usage:
    client = get_vllm_client()
    # Single request
    result = await client.generate("Patient reports chest pain...")
    # Streaming
    async for token in client.generate_stream("Patient reports..."):
        print(token, end="")
"""

from __future__ import annotations

import logging
import time
from typing import Any, AsyncIterator, Dict, List, Optional

from app.config import settings

logger = logging.getLogger(__name__)


class VLLMClient:
    """Client for vLLM OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:8001",
        model_name: str = "google/medgemma-4b-it",
        api_key: str = "EMPTY",
    ):
        self._base_url = base_url.rstrip("/")
        self._model = model_name
        self._api_key = api_key
        self._client = None
        self._available = False
        self._init_client()

    def _init_client(self) -> None:
        """Initialize the async HTTP client."""
        try:
            import httpx
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=120.0,
                headers={"Authorization": f"Bearer {self._api_key}"},
            )
            self._available = True
            logger.info(f"vLLM client initialized: {self._base_url}, model={self._model}")
        except ImportError:
            logger.warning("httpx not installed for vLLM client")
        except Exception as e:
            logger.warning(f"vLLM client init failed: {e}")

    @property
    def is_available(self) -> bool:
        return self._available

    async def health_check(self) -> Dict[str, Any]:
        """Check vLLM server health."""
        if not self._client:
            return {"healthy": False, "error": "client not initialized"}
        try:
            resp = await self._client.get("/health")
            return {"healthy": resp.status_code == 200}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    async def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        top_p: float = 1.0,
        repetition_penalty: float = 1.15,
        stop: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate text via vLLM completions endpoint.

        Args:
            prompt: Input prompt text.
            max_tokens: Maximum tokens to generate.
            temperature: Sampling temperature (0 = greedy).
            top_p: Nucleus sampling threshold.
            repetition_penalty: Repetition penalty factor.
            stop: Stop sequences.

        Returns:
            Dict with text, usage, latency.
        """
        if not self._client:
            return {"error": "vLLM client not available"}

        start = time.time()

        try:
            payload = {
                "model": self._model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "top_p": top_p,
                "repetition_penalty": repetition_penalty,
                "stop": stop or [],
            }

            resp = await self._client.post("/v1/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            usage = data.get("usage", {})

            return {
                "text": choice["text"],
                "finish_reason": choice.get("finish_reason", ""),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "latency_ms": round((time.time() - start) * 1000, 1),
            }

        except Exception as e:
            logger.error(f"vLLM generation failed: {e}")
            return {"error": str(e), "latency_ms": round((time.time() - start) * 1000, 1)}

    async def generate_stream(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
        repetition_penalty: float = 1.15,
    ) -> AsyncIterator[str]:
        """Stream tokens from vLLM.

        Yields:
            Individual tokens as they're generated.
        """
        if not self._client:
            yield "[ERROR: vLLM client not available]"
            return

        try:
            payload = {
                "model": self._model,
                "prompt": prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "repetition_penalty": repetition_penalty,
                "stream": True,
            }

            async with self._client.stream(
                "POST", "/v1/completions", json=payload
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        import json
                        try:
                            data = json.loads(data_str)
                            token = data["choices"][0].get("text", "")
                            if token:
                                yield token
                        except (json.JSONDecodeError, KeyError):
                            continue

        except Exception as e:
            logger.error(f"vLLM streaming failed: {e}")
            yield f"[ERROR: {e}]"

    async def generate_chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Generate via OpenAI chat completions endpoint.

        Args:
            messages: List of {"role": ..., "content": ...} messages.

        Returns:
            Dict with text and metadata.
        """
        if not self._client:
            return {"error": "vLLM client not available"}

        start = time.time()

        try:
            payload = {
                "model": self._model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }

            resp = await self._client.post("/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

            choice = data["choices"][0]
            return {
                "text": choice["message"]["content"],
                "finish_reason": choice.get("finish_reason", ""),
                "usage": data.get("usage", {}),
                "latency_ms": round((time.time() - start) * 1000, 1),
            }

        except Exception as e:
            logger.error(f"vLLM chat generation failed: {e}")
            return {"error": str(e)}

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()


# Singleton
_vllm_client: Optional[VLLMClient] = None


def get_vllm_client() -> VLLMClient:
    global _vllm_client
    if _vllm_client is None:
        vllm_url = getattr(settings, "vllm_url", "http://localhost:8001")
        model = getattr(settings, "vllm_model", settings.medgemma_model)
        _vllm_client = VLLMClient(base_url=vllm_url, model_name=model)
    return _vllm_client
