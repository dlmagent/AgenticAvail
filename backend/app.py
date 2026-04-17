from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.availability import SearchRequest, search_hotels
from services.context import UpsertRequest, get_session_state, upsert_session
from services.extraction import ExtractRequest, extract_patch
from services.mcp import InvokeRequest, InvokeResponse, list_capabilities, invoke_capability
from services.orchestrator import ChatRequest, ChatResponse, MODEL, chat, chat_react
from services.property_resolver import ResolveRequest, ResolveResponse, resolve_property
from services.results_explainer import ExplainRequest, ExplainResponse, explain_results


app = FastAPI(title="Unified Hotel Demo Backend", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"ok": True, "model": MODEL, "deployment": "unified-backend"}


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
