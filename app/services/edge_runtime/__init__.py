"""
ONNX Edge Deployment Runtime (Phase 4)

Exports MedGemma and faster-whisper models to ONNX format for
edge/mobile deployment with 2x inference speed improvement.

Supports:
- ONNX Runtime (CPU/GPU/TensorRT)
- Quantized INT8 models for mobile
- WebAssembly via onnxruntime-web
"""
