from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field


class SessionState(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    check_in: Optional[date] = None
    check_out: Optional[date] = None
    nights: Optional[int] = None
    month: Optional[int] = None
    year: Optional[int] = None
    rooms: int = 1
    guests: int = 2
    neighborhood: Optional[str] = None
    required_amenities: List[str] = Field(default_factory=list)
    preferred_amenities: List[str] = Field(default_factory=list)
    max_nightly_rate_usd: Optional[float] = None
    max_total_usd: Optional[float] = None
    sort_by: str = "best_value"
    poi_query: Optional[str] = None
    poi_radius_miles: Optional[float] = None
    poi_lat: Optional[float] = None
    poi_lng: Optional[float] = None
    poi_resolved: bool = False
    poi_last_resolved_query: Optional[str] = None


class UpsertRequest(BaseModel):
    session_id: str
    patch: dict = Field(default_factory=dict)


class UpsertResponse(BaseModel):
    session_id: str
    state: SessionState


SESSIONS: Dict[str, SessionState] = {}


def _canon(values) -> List[str]:
    if values is None:
        return []
    if not isinstance(values, list):
        values = [values]
    normalized = []
    for value in values:
        text = str(value).strip().lower()
        if text:
            normalized.append(text)
    seen = set()
    unique: List[str] = []
    for item in normalized:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def get_session_state(session_id: str) -> SessionState:
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="session not found")
    return SESSIONS[session_id]


def upsert_session(request: UpsertRequest) -> UpsertResponse:
    state = SESSIONS.get(request.session_id, SessionState())
    patch = request.patch or {}

    for field in ["city", "state", "neighborhood", "sort_by", "poi_query", "poi_last_resolved_query"]:
        if field in patch:
            setattr(state, field, patch[field])

    for field in ["rooms", "guests", "month", "year"]:
        if field in patch and patch[field] is not None:
            setattr(state, field, int(patch[field]))

    if "nights" in patch:
        state.nights = int(patch["nights"]) if patch["nights"] is not None else None

    for field in ["check_in", "check_out"]:
        if field in patch:
            setattr(state, field, patch[field])

    if "required_amenities" in patch:
        state.required_amenities = _canon(patch.get("required_amenities"))
    if "preferred_amenities" in patch:
        state.preferred_amenities = _canon(patch.get("preferred_amenities"))

    for field in ["max_nightly_rate_usd", "max_total_usd", "poi_radius_miles", "poi_lat", "poi_lng"]:
        if field in patch:
            setattr(state, field, float(patch[field]) if patch[field] is not None else None)

    if "poi_resolved" in patch:
        state.poi_resolved = bool(patch["poi_resolved"])

    SESSIONS[request.session_id] = state
    return UpsertResponse(session_id=request.session_id, state=state)
