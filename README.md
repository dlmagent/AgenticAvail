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
