# Deploying AnomalEye

The whole product — API **and** the built React UI — runs from a single
container via the root `Dockerfile`. A multi-stage build compiles the frontend,
then FastAPI serves both the API and the static assets on one port. The image
reads the platform-provided `$PORT`, so it drops straight into Render, Railway,
Fly.io, or any Docker host.

---

## Option A — Render (recommended, free tier, deploys from GitHub)

The repo ships a `render.yaml` blueprint, so this is a few clicks:

1. Push to GitHub (already done: `PerinbaBuilds/AnomalEye`).
2. Go to <https://dashboard.render.com> → **New +** → **Blueprint**.
3. Connect the `AnomalEye` repo. Render reads `render.yaml` and proposes a
   Docker web service named **anomaleye** on the free plan.
4. Click **Apply**. First build takes ~3–5 min (installs deps + builds the UI).
5. Your app is live at `https://anomaleye.onrender.com` (or the URL Render
   assigns). Health check: `/api/health`.

> Free instances sleep after ~15 min idle and cold-start on the next request
> (~30 s). Upgrade the plan for always-on.

Alternatively, without the blueprint: **New +** → **Web Service** → connect the
repo → Render auto-detects the `Dockerfile` → set health check path to
`/api/health` → **Create**.

---

## Option B — Railway (fast, generous trial)

1. <https://railway.app> → **New Project** → **Deploy from GitHub repo**.
2. Pick `AnomalEye`. Railway detects the `Dockerfile` and builds it.
3. Once deployed, open **Settings → Networking → Generate Domain** to get a
   public URL. Railway injects `$PORT` automatically.

---

## Option C — Fly.io (global, needs the CLI)

```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth login

# from the repo root
fly launch --no-deploy      # accept the detected Dockerfile; sets internal_port 8000
fly deploy
```

Make sure `fly.toml` has `internal_port = 8000` (matches the Dockerfile).

---

## Option D — Run the container locally

```bash
docker build -t anomaleye .
docker run -p 8000:8000 anomaleye
# open http://localhost:8000
```

---

## Split deploy (optional): static frontend + separate API

If you prefer a CDN-hosted frontend (Vercel/Netlify/GitHub Pages) with the API
elsewhere:

1. Deploy the API (this `Dockerfile`, minus the frontend copy) to Render/Railway.
2. In `frontend/src/api/client.ts`, change `const BASE = "/api"` to your API's
   absolute URL (e.g. `https://anomaleye-api.onrender.com/api`).
3. Add that origin to the CORS `allow_origins` list in `backend/main.py`.
4. `cd frontend && npm run build` and deploy `frontend/dist` to your static host.

The single-container option above is simpler and is what `render.yaml` uses.

---

## Notes

- The committed `data/*.csv` are baked into the image, so no dataset generation
  happens at boot — the first request is fast once the startup analysis pass
  (~5–10 s) completes.
- No secrets or API keys are required; the engine is fully offline and
  deterministic.
