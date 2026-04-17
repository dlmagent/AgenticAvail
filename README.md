# Hotel Agentic AI Demo

The active deployment layout is now:

- `frontend/`: React UI
- `backend/`: one FastAPI deployable that runs the orchestrator, MCP layer, context agent, extraction agent, availability agent, property resolver, and results explainer together in-process

The old split-service folders are still present as reference, but the new runtime path is the frontend plus unified backend pair.

## Ports

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000`

## Run locally

Set `OPENAI_API_KEY` in your shell, then run:

```powershell
.\rundemo.ps1
```

## Run with Docker

```powershell
docker compose up --build
```

## Deploy To Render

This repo includes [render.yaml](/c:/dev/python/AgenticAvail/render.yaml) for a two-service Render setup:

- `agenticavail-backend`: FastAPI web service
- `agenticavail-frontend`: Vite/React static site

Backend env vars to set in Render:

- `OPENAI_API_KEY`: required
- `OPENAI_MODEL`: optional, defaults to `gpt-4.1`
- `CORS_ALLOWED_ORIGINS`: required for separate frontend/backend deploys
  Example: `https://your-frontend-name.onrender.com`

Frontend env vars to set in Render:

- `VITE_API_BASE_URL`: required
  Example: `https://your-backend-name.onrender.com`

Recommended Render flow:

1. Push this repo to GitHub.
2. In Render, create a new Blueprint from the repo.
3. Set the required environment variables when prompted.
4. After the backend is created, copy its public URL into the frontend `VITE_API_BASE_URL`.
5. Set the backend `CORS_ALLOWED_ORIGINS` to the frontend public URL.
6. Redeploy both services.

## Backend endpoints

- `GET /health`
- `POST /chat`
- `POST /chat/react`
- `GET /capabilities`
- `POST /invoke`

Direct embedded-service routes are also available:

- `GET /context/session/{session_id}`
- `POST /context/upsert`
- `POST /agents/extract`
- `POST /agents/search`
- `POST /agents/resolve`
- `POST /agents/explain`

## Notes

- The MCP contract is preserved, but capability routing is now in-process instead of hop-by-hop HTTP between separate containers.
- The React app can target a separately hosted backend by setting `VITE_API_BASE_URL`.
- `REACT_IMPLEMENTATION.md` and `ARCHITECTURE_COMPARISON.md` still describe the orchestration behavior; only the deployment topology changed.
