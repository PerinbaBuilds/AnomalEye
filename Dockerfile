# Multi-stage build: compile the React frontend, then run FastAPI serving both
# the API and the built static assets from a single container.

# ---- Stage 1: build the frontend ----
FROM node:20-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: python runtime ----
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Application code + committed dataset (so no generation is needed at boot).
COPY anomaleye/ ./anomaleye/
COPY backend/ ./backend/
COPY data/ ./data/

# Built frontend from stage 1.
COPY --from=frontend /app/frontend/dist ./frontend/dist

EXPOSE 8000
# Respect the platform-provided $PORT (Render/Railway/Fly set this).
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
