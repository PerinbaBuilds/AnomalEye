# Deploying AnomalEye

The whole product — API **and** the built React UI — runs from a single
container via the root `Dockerfile`. A multi-stage build compiles the frontend,
then FastAPI serves both the API and the static assets on one port. The image
reads the platform-provided `$PORT`, so it drops straight into any Docker host.

## Which platform?

| Platform | Free? | Card needed? | Notes |
|---|---|---|---|
| **Render** | ✅ free web service | ❌ no | `render.yaml` included. Sleeps when idle. **Currently deployed here.** |
| **Fly.io** | ✅ small allowance | ⚠️ yes | CLI-based; `fly.toml` included. |
| **Hugging Face Spaces** | ⚠️ Docker needs PRO | 💲 | Docker Spaces now require a PRO subscription. |

Everything runs locally with no account at all (`docker run` or the dev
scripts) — deployment is only needed for a public URL.

The live deployment is on **Render** (Option A below). The Hugging Face manual
route is kept for reference but note Docker Spaces are no longer free.

---

## Hugging Face Spaces, manual (Docker Spaces now require PRO)

Spaces run your `Dockerfile` directly, but as of 2026 free `cpu-basic` no longer
hosts Docker Spaces without a PRO subscription.

1. Create a free account at <https://huggingface.co>.
2. **New** → **Space** → name it `anomaleye` → **SDK: Docker** → **Blank** →
   Create. This makes a git repo at
   `https://huggingface.co/spaces/<you>/anomaleye`.
3. Edit that Space's `README.md` (top of the file) so its frontmatter has the
   app port:

   ```yaml
   ---
   title: AnomalEye
   emoji: 👁
   colorFrom: red
   colorTo: gray
   sdk: docker
   app_port: 8000
   ---
   ```
4. Push this project's code into the Space repo:

   ```bash
   git clone https://huggingface.co/spaces/<you>/anomaleye hf-space
   cd hf-space
   # copy everything from this repo EXCEPT its README.md (keep the Space's)
   #   ...copy Dockerfile, anomaleye/, backend/, frontend/, data/, requirements.txt...
   git add . && git commit -m "Deploy AnomalEye" && git push
   ```
5. The Space builds the Docker image and goes live. To enable the LLM agent:
   Space **Settings → Variables and secrets** → add `GROQ_API_KEY`.

---

## Option B — Fly.io (CLI)

```bash
curl -L https://fly.io/install.sh | sh   # one-time
fly auth login
fly launch --no-deploy      # accept the included fly.toml
fly secrets set GROQ_API_KEY=your_key     # optional
fly deploy
```

The included `fly.toml` sets `internal_port = 8000` and 1 GB RAM.

---

## Option A — Render (recommended · currently live)

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

### Enabling the LLM agent on the deployed app

The `render.yaml` declares `GROQ_API_KEY` as a **secret** (`sync: false`), so
it is never in git. After the first deploy:

1. Open the **anomaleye** service → **Environment**.
2. Add `GROQ_API_KEY` = your key from <https://console.groq.com/keys>.
3. Save — Render redeploys. The Agent Console now shows the **LLM agent** badge.

Without the key the deployed app still works using the rule-based planner.
(Same idea on Railway/Fly: add `GROQ_API_KEY` in the service's variables.)

---

## Option C — Railway (fast, generous trial)

1. <https://railway.app> → **New Project** → **Deploy from GitHub repo**.
2. Pick `AnomalEye`. Railway detects the `Dockerfile` and builds it.
3. Once deployed, open **Settings → Networking → Generate Domain** to get a
   public URL. Railway injects `$PORT` automatically; add `GROQ_API_KEY` under
   **Variables**.

---

## Run the container locally (no account)

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
