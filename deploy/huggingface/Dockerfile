# HF Spaces Dockerfile — backend-only, free CPU tier compatible.
#
# Strategy:
#   - Loads no models locally; routes MedGemma generation to HF Inference Providers.
#   - Uses CPU torch wheels (small footprint) since transformers is still imported
#     transitively even when MEDGEMMA_PROVIDER=hf-inference.
#   - Exposes 7860 (HF Spaces default app_port).
#
# Build context expected: the repo root (this Dockerfile referenced from the
# Space repo's root Dockerfile pointer, or copy this file to the Space root).

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HOME=/home/user \
    HF_HOME=/home/user/.cache/huggingface

# System deps for audio + scispacy
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ffmpeg \
        libsndfile1 \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

# HF Spaces requires non-root user
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app

# Install Python deps (CPU-only torch from PyTorch's CPU index)
COPY --chown=user:user requirements.txt ./
RUN pip install --user --upgrade pip && \
    pip install --user --index-url https://download.pytorch.org/whl/cpu torch==2.2.1 torchaudio==2.2.1 && \
    pip install --user -r requirements.txt

# App code
COPY --chown=user:user . .

# HF Spaces sets PORT but app_port in README.md frontmatter pins it to 7860.
ENV PATH="/home/user/.local/bin:${PATH}" \
    DEVICE=cpu \
    ENABLE_GPU=false \
    MEDGEMMA_PROVIDER=hf-inference \
    DEPLOYMENT_MODE=development \
    API_HOST=0.0.0.0 \
    API_PORT=7860 \
    ENABLE_IMAGE_ANALYSIS=false

EXPOSE 7860

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
