---
title: VoxDoc Voice Symptom Triage Assistant
emoji: 🩺
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
short_description: Voice intake and clinical documentation demo
---

# VoxDoc — HF Space Deployment

Demo deployment of [voice-symptom-triage-assistant](https://github.com/JoelJohnsonThomas/voice-symptom-triage-assistant) on Hugging Face Spaces.

> **Demo only.** Hugging Face Spaces are **not HIPAA-compliant**. Do not submit
> real protected health information (PHI). Use synthetic transcripts only.

## How this Space is configured

This Space runs the FastAPI backend on the **free CPU tier**. To stay within
the 2-vCPU / 16-GB RAM budget, MedGemma generation is delegated to **HF
Inference Providers** rather than loaded in-process. ASR (`whisper-small`)
and biomedical NER still run locally on CPU.

| Setting | Value | Why |
|---|---|---|
| `MEDGEMMA_PROVIDER` | `hf-inference` | Avoid loading the 4b model on CPU |
| `DEVICE` / `ENABLE_GPU` | `cpu` / `false` | Free tier has no GPU |
| `ENABLE_IMAGE_ANALYSIS` | `false` | Vision routing not configured here |
| `app_port` | `7860` | HF Spaces default |

## Required Space secrets

Add these in **Settings → Variables and secrets → New secret**:

- `HF_TOKEN` — read-token from [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) with access to MedGemma
- `ENCRYPTION_MASTER_KEY` — any strong random string (`openssl rand -hex 32`)
- `JWT_SECRET_KEY` — same; used even with auth disabled

## Optional: persist sessions across restarts

The default SQLite store lives on the ephemeral Space filesystem and is lost
on restart. To keep sessions, either:

1. Enable **persistent storage** (Settings → paid feature) and point
   the SQLite file at `/data/voxdoc.db`, **or**
2. Set `DATABASE_URL` to a free hosted Postgres (Neon / Supabase) using the
   `postgresql+asyncpg://...` form.

## Frontend

The React frontend (`frontend/`) is **not** built into this Space — deploy it
separately to Vercel/Netlify and point its API base URL at this Space's URL.
The legacy server-rendered UI under `app/static/` is still reachable for
quick testing.

## Local equivalent

```bash
docker build -f deploy/huggingface/Dockerfile -t voxdoc-hf .
docker run -p 7860:7860 \
  -e HF_TOKEN=hf_xxx \
  -e ENCRYPTION_MASTER_KEY=$(openssl rand -hex 32) \
  -e JWT_SECRET_KEY=$(openssl rand -hex 32) \
  voxdoc-hf
```

Open [http://localhost:7860](http://localhost:7860).
