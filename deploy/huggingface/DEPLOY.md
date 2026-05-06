# Deploying VoxDoc to Hugging Face Spaces (free tier)

Step-by-step. Total time: ~10 minutes plus build.

## 1. Create the Space

1. Go to [huggingface.co/new-space](https://huggingface.co/new-space).
2. Name it (e.g. `voxdoc-demo`).
3. **SDK**: Docker → "Blank".
4. **Hardware**: CPU basic (free).
5. Create.

## 2. Add secrets

In **Space → Settings → Variables and secrets**, add:

| Name | Value |
|---|---|
| `HF_TOKEN` | Read token with MedGemma access |
| `ENCRYPTION_MASTER_KEY` | `openssl rand -hex 32` |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `DATABASE_URL` *(optional)* | Postgres URL if you want persistence |

## 3. Push the code

The Space is its own git repo. Two options:

### Option A — push the whole repo

```bash
# Replace with your Space URL
git remote add space https://huggingface.co/spaces/<user>/voxdoc-demo

# HF Spaces expects Dockerfile + README.md at the repo root.
# Stage the deploy artifacts there:
cp deploy/huggingface/Dockerfile ./Dockerfile.hfspace
cp deploy/huggingface/README.md ./README.hfspace.md

# Push to the Space's main branch.
# (HF expects the file named exactly "Dockerfile" and "README.md" at root.
#  Either rename in a deploy branch, or use Option B below.)
```

### Option B — push only the Space subset (recommended)

Create a deploy branch that has the Dockerfile + README.md at root:

```bash
git checkout -b hf-space
mv deploy/huggingface/Dockerfile ./Dockerfile
mv deploy/huggingface/README.md ./README.md
git add Dockerfile README.md
git commit -m "HF Space build artifacts at root"
git remote add space https://huggingface.co/spaces/<user>/voxdoc-demo
git push space hf-space:main
```

Switch back to `master` afterwards — the deploy branch is just for HF.

## 4. Watch the build

In the Space's **Logs** tab. First build is ~5–10 min (CPU torch + scispacy
models). Once `Application startup complete` appears, hit the Space URL.

## 5. Verify

```
GET https://<user>-voxdoc-demo.hf.space/health
```

Should return `{"status": "ok", ...}`. Then load the legacy UI at the root
URL, or point your Vercel-hosted React frontend at this base URL.

## Troubleshooting

- **Build out-of-memory**: drop the `peft`, `chromadb`, or `presidio-*` lines
  from `requirements.txt` if you don't need them — they pull in heavy deps.
- **MedGemma 401/403**: your `HF_TOKEN` lacks access. Visit the model page
  and accept the Gemma terms first.
- **Slow first request**: free Spaces sleep on inactivity; first call after
  sleep takes 30–60s to spin up. Subsequent calls are normal speed.
- **`No module named 'app'`**: ensure the Dockerfile's `WORKDIR` is the dir
  containing `app/` (it is, by default).
