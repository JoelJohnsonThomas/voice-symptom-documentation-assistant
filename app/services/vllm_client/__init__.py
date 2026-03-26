"""
vLLM Production Serving Client (Phase 4)

High-throughput LLM inference via vLLM with:
- Continuous batching (3-5x throughput vs HuggingFace generate())
- PagedAttention for efficient KV-cache management
- AWQ/GPTQ quantization support
- OpenAI-compatible API for drop-in replacement

Falls back to local HuggingFace inference if vLLM is unavailable.
"""
