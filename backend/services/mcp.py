from __future__ import annotations

import time
import uuid
from typing import Any, Dict, Optional

from fastapi import HTTPException
from jsonschema import ValidationError, validate
from pydantic import BaseModel, Field

from .availability import SearchRequest, search_hotels
from .context import UpsertRequest, get_session_state, upsert_session
from .extraction import ExtractRequest, extract_patch
from .property_resolver import ResolveRequest, resolve_property
from .results_explainer import ExplainRequest, explain_results


def capability_map() -> Dict[str, Dict[str, Any]]:
    return {
        "context.get": {
            "name": "context.get",
            "description": "Fetch current session state for the given session_id.",
            "input_schema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}},
                "required": ["session_id"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: get_session_state(arguments["session_id"]).model_dump(mode="json"),
        },
        "context.upsert": {
            "name": "context.upsert",
            "description": "Apply a patch to session state and return updated state.",
            "input_schema": {
                "type": "object",
                "properties": {"session_id": {"type": "string"}, "patch": {"type": "object"}},
                "required": ["session_id", "patch"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: upsert_session(UpsertRequest(**arguments)).model_dump(mode="json"),
        },
        "property.resolve": {
            "name": "property.resolve",
            "description": "Resolve a place/POI name to geo data and candidate hotels.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "city": {"type": "string"},
                    "state": {"type": ["string", "null"]},
                    "radius_miles": {"type": ["number", "null"]},
                },
                "required": ["query", "city"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: resolve_property(ResolveRequest(**arguments)).model_dump(mode="json"),
        },
        "availability.search": {
            "name": "availability.search",
            "description": "Search fake hotel availability + pricing + amenities.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "city": {"type": "string"},
                    "state": {"type": ["string", "null"]},
                    "check_in": {"type": "string"},
                    "check_out": {"type": "string"},
                    "rooms": {"type": "integer"},
                    "guests": {"type": "integer"},
                    "neighborhood": {"type": ["string", "null"]},
                    "required_amenities": {"type": ["array", "null"], "items": {"type": "string"}},
                    "preferred_amenities": {"type": ["array", "null"], "items": {"type": "string"}},
                    "max_nightly_rate_usd": {"type": ["number", "null"]},
                    "max_total_usd": {"type": ["number", "null"]},
                    "poi_lat": {"type": ["number", "null"]},
                    "poi_lng": {"type": ["number", "null"]},
                    "sort_by": {"type": ["string", "null"]},
                },
                "required": ["city", "check_in", "check_out", "rooms", "guests"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: search_hotels(SearchRequest(**arguments)).model_dump(mode="json"),
        },
        "extraction.parse": {
            "name": "extraction.parse",
            "description": "Extract intent + a partial patch from a user message to update session context.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "user_message": {"type": "string"},
                    "state": {"type": "object"},
                },
                "required": ["session_id", "user_message", "state"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: extract_patch(ExtractRequest(**arguments)).model_dump(mode="json"),
        },
        "results.explain": {
            "name": "results.explain",
            "description": "Explain availability search results (grounded).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "session_id": {"type": "string"},
                    "user_message": {"type": "string"},
                    "state": {"type": "object"},
                    "search_response": {"type": "object"},
                },
                "required": ["session_id", "user_message", "state", "search_response"],
                "additionalProperties": False,
            },
            "handler": lambda arguments: explain_results(ExplainRequest(**arguments)).model_dump(mode="json"),
        },
    }


CAPABILITIES = capability_map()


class InvokeRequest(BaseModel):
    capability: str = Field(..., examples=["availability.search"])
    arguments: Dict[str, Any] = Field(default_factory=dict)
    trace_id: Optional[str] = None


class InvokeResponse(BaseModel):
    trace_id: str
    capability: str
    ok: bool
    elapsed_ms: int
    result: Any = None
    error: Optional[str] = None


class LocalMCPClient:
    def list_capabilities(self) -> Dict[str, Any]:
        return {"ok": True, "status_code": 200, "result": list_capabilities()}

    def invoke(self, capability: str, arguments: Dict[str, Any], trace_id: Optional[str] = None) -> Dict[str, Any]:
        try:
            response = invoke_capability(InvokeRequest(capability=capability, arguments=arguments or {}, trace_id=trace_id))
            return response.model_dump(mode="json") | {"status_code": 200 if response.ok else 500}
        except HTTPException as exc:
            return {
                "trace_id": trace_id,
                "capability": capability,
                "ok": False,
                "elapsed_ms": 0,
                "result": None,
                "error": exc.detail,
                "status_code": exc.status_code,
            }


def list_capabilities() -> list[Dict[str, Any]]:
    return [
        {"name": capability["name"], "description": capability["description"], "input_schema": capability["input_schema"]}
        for capability in CAPABILITIES.values()
    ]


def invoke_capability(request: InvokeRequest) -> InvokeResponse:
    trace_id = request.trace_id or str(uuid.uuid4())
    start = time.time()

    if request.capability not in CAPABILITIES:
        raise HTTPException(status_code=404, detail=f"Unknown capability: {request.capability}")

    capability = CAPABILITIES[request.capability]
    try:
        validate(instance=request.arguments, schema=capability["input_schema"])
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid arguments for {request.capability}: {exc.message}")

    try:
        result = capability["handler"](request.arguments)
        elapsed_ms = int((time.time() - start) * 1000)
        return InvokeResponse(trace_id=trace_id, capability=request.capability, ok=True, elapsed_ms=elapsed_ms, result=result)
    except HTTPException:
        raise
    except Exception as exc:
        elapsed_ms = int((time.time() - start) * 1000)
        return InvokeResponse(trace_id=trace_id, capability=request.capability, ok=False, elapsed_ms=elapsed_ms, error=str(exc))
