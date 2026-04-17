from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from services.availability import SearchRequest, search_hotels
from services.context import UpsertRequest, get_session_state, upsert_session
from services.extraction import ExtractRequest, extract_patch
from services.mcp_facade import MCP_FACADE_AVAILABLE, MCP_FACADE_IMPORT_ERROR, mcp_http_app, mcp_server
from services.mcp import InvokeRequest, InvokeResponse, list_capabilities, invoke_capability
from services.orchestrator import ChatRequest, ChatResponse, MODEL, chat, chat_react
from services.property_resolver import ResolveRequest, ResolveResponse, resolve_property
from services.results_explainer import ExplainRequest, ExplainResponse, explain_results


def _cors_allowed_origins() -> list[str]:
    raw = (os.getenv("CORS_ALLOWED_ORIGINS") or "").strip()
    if not raw:
        return ["*"]
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


allowed_origins = _cors_allowed_origins()
mcp_auth_token = (os.getenv("MCP_AUTH_TOKEN") or "").strip()


@asynccontextmanager
async def app_lifespan(_app: FastAPI):
    if MCP_FACADE_AVAILABLE and mcp_server is not None:
        async with mcp_server.session_manager.run():
            yield
        return
    yield


app = FastAPI(title="Unified Hotel Demo Backend", version="1.0", lifespan=app_lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allowed_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Mcp-Session-Id"],
)


@app.middleware("http")
async def protect_mcp_facade(request: Request, call_next):
    if request.url.path.startswith("/mcp") and mcp_auth_token:
        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {mcp_auth_token}"
        if authorization != expected:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized MCP request"})
    return await call_next(request)


@app.get("/health")
def health():
    return {
        "ok": True,
        "model": MODEL,
        "deployment": "unified-backend",
        "mcp_facade": {
            "enabled": MCP_FACADE_AVAILABLE,
            "path": "/mcp",
            "auth_required": bool(mcp_auth_token),
            "import_error": MCP_FACADE_IMPORT_ERROR,
        },
    }


if MCP_FACADE_AVAILABLE and mcp_http_app is not None:
    app.mount("/mcp", mcp_http_app)


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(request: ChatRequest):
    return chat(request)


@app.post("/chat/react", response_model=ChatResponse)
def chat_react_endpoint(request: ChatRequest):
    return chat_react(request)


@app.get("/capabilities")
def capabilities_endpoint():
    return list_capabilities()


@app.post("/invoke", response_model=InvokeResponse)
def invoke_endpoint(request: InvokeRequest):
    return invoke_capability(request)


@app.get("/context/session/{session_id}")
def get_session_endpoint(session_id: str):
    return get_session_state(session_id)


@app.post("/context/upsert")
def upsert_session_endpoint(request: UpsertRequest):
    return upsert_session(request)


@app.post("/agents/extract")
def extract_endpoint(request: ExtractRequest):
    return extract_patch(request)


@app.post("/agents/search")
def search_endpoint(request: SearchRequest):
    return search_hotels(request)


@app.post("/agents/resolve", response_model=ResolveResponse)
def resolve_endpoint(request: ResolveRequest):
    return resolve_property(request)


@app.post("/agents/explain", response_model=ExplainResponse)
def explain_endpoint(request: ExplainRequest):
    return explain_results(request)
