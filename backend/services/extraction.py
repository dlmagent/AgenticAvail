from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Literal, Optional

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field


MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
ALLOWED_NEIGHBORHOODS = ["Downtown", "Midtown", "Buckhead", "Airport", "O4W"]
ALLOWED_AMENITIES = ["spa", "restaurant", "swimming pool", "fitness facility", "pet friendly"]
DEMO_CITY = "Atlanta"
DEMO_STATE = "GA"
DEMO_MONTH = 6
DEMO_YEAR = 2026
MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
DAY_OF_MONTH_RE = re.compile(r"\b(?:around|about|roughly|near)?\s*(?:the\s*)?(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
NEAR_RE = re.compile(r"\b(?:near|around|by|close to)\s+(.+)$", re.IGNORECASE)
RADIUS_RE = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:mi|mile|miles)\b", re.IGNORECASE)
BROADEN_RE = re.compile(r"\b(anywhere|any area|all of atlanta|no preference|doesn'?t matter|not near|ignore proximity|remove proximity|broaden|widen)\b", re.IGNORECASE)
NIGHTS_RE = re.compile(r"\bfor\s+(\d{1,2})\s+nights?\b", re.IGNORECASE)
GUESTS_RE = re.compile(r"\b(\d{1,2})\s*(?:adults?|guests?|people|persons?)\b", re.IGNORECASE)
CHEAP_TOTAL_RE = re.compile(r"\b(cheapest|lowest total|lowest overall)\b", re.IGNORECASE)
LOWEST_NIGHTLY_RE = re.compile(r"\b(lowest nightly|cheapest nightly|lowest per night)\b", re.IGNORECASE)
CLOSEST_RE = re.compile(r"\b(closest|nearest)\b", re.IGNORECASE)
SYSTEM_PROMPT = f"""You are an Extraction Agent for a hotel search assistant.

Your job: turn the user's free-text message into a STRUCTURED PATCH to update session state, plus a coarse intent.

Important:
- Output MUST be valid JSON only (no markdown).
- Do NOT hallucinate. Only extract what the user implies.
- This demo supports only Atlanta, GA and June 2026. If user gives a different city/date, still extract it, but do not correct it.
- Dates:
  - If user gives "June 10-13 2026" interpret as check_in=2026-06-10, check_out=2026-06-13
  - If user gives "June 17 for 4 nights" output check_in=2026-06-17 and nights=4 (do NOT compute check_out here; orchestrator will).
  - If user says only "in June" (no specific day), extract month=6 and year=2026 for demo context.
  - If user says "around the 10th" and month/year context exists, extract check_in for that day; do not invent check_out unless explicitly stated.
- Guests:
  - "3 adults" => guests=3
- Rooms:
  - If not specified, omit (do not default here).
- Amenities:
  - Map synonyms: pool->swimming pool, gym->fitness facility, pet-friendly/pets allowed->pet friendly
  - required_amenities for "must have", preferred_amenities for "prefer/nice to have".
  - Keep amenities within: {ALLOWED_AMENITIES}
- Neighborhood:
  - If user mentions one of {ALLOWED_NEIGHBORHOODS}, set neighborhood.
- Sorting:
  - "cheapest" or "lowest total" => sort_by="lowest_total"
  - "lowest nightly" => sort_by="lowest_avg_nightly"
  - Otherwise omit.

Return JSON with:
{{
  "intent": "availability_search" | "refine_search" | "other",
  "patch": {{ ... }},
  "confidence": 0.0-1.0
}}
"""


class ExtractRequest(BaseModel):
    session_id: str
    user_message: str
    state: Dict[str, Any] = Field(default_factory=dict)


class ExtractResponse(BaseModel):
    intent: Literal["availability_search", "refine_search", "other"]
    patch: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = 0.6


def _safe_json_loads(payload: str) -> Dict[str, Any]:
    try:
        return json.loads(payload)
    except Exception:
        if not payload:
            return {}
        start = payload.find("{")
        end = payload.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(payload[start : end + 1])
            except Exception:
                return {}
        return {}


def _norm_amenity(amenity: str) -> str:
    amenity = (amenity or "").strip().lower()
    if amenity == "pool":
        return "swimming pool"
    if amenity == "gym":
        return "fitness facility"
    if amenity in {"pet-friendly", "pets allowed", "pet friendly hotel", "pet friendly hotels"}:
        return "pet friendly"
    return amenity


def _canon_amen_list(values: Any) -> List[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    result: List[str] = []
    for value in values:
        normalized = _norm_amenity(str(value))
        if normalized in ALLOWED_AMENITIES and normalized not in result:
            result.append(normalized)
    return result


def _detect_month_year_from_text(text: str) -> Optional[Dict[str, int]]:
    lowered = text.lower()
    for month_name, month_number in MONTH_MAP.items():
        if re.search(rf"\b{month_name}\b", lowered):
            return {"month": month_number, "year": DEMO_YEAR}
    return None


def _day_of_month_from_text(text: str) -> Optional[int]:
    match = DAY_OF_MONTH_RE.search(text)
    if not match:
        return None
    day = int(match.group(1))
    return day if 1 <= day <= 31 else None


def _nights_from_text(text: str) -> Optional[int]:
    match = NIGHTS_RE.search(text)
    if not match:
        return None
    nights = int(match.group(1))
    return nights if 1 <= nights <= 30 else None


def _guests_from_text(text: str) -> Optional[int]:
    match = GUESTS_RE.search(text)
    if not match:
        return None
    guests = int(match.group(1))
    return guests if 1 <= guests <= 10 else None


def _sort_from_text(text: str) -> Optional[str]:
    if CLOSEST_RE.search(text):
        return "closest_to_poi"
    if CHEAP_TOTAL_RE.search(text):
        return "lowest_total"
    if LOWEST_NIGHTLY_RE.search(text):
        return "lowest_avg_nightly"
    return None


def _infer_intent(user_message: str, patch: Dict[str, Any]) -> str:
    lowered = (user_message or "").lower()
    if any(key in patch for key in ("check_in", "check_out", "nights", "required_amenities", "preferred_amenities", "sort_by", "guests", "neighborhood", "poi_query")):
        return "availability_search"
    if any(token in lowered for token in ("available", "availability", "hotels", "room", "stay", "book")):
        return "availability_search"
    return "other"


def extract_patch(request: ExtractRequest) -> ExtractResponse:
    try:
        client = OpenAI()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Current state (JSON):\n"
                    + json.dumps(request.state, default=str)
                    + "\n\nUser message:\n"
                    + request.user_message,
                },
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        data = _safe_json_loads(content)
        intent = data.get("intent") or "other"
        if intent not in ("availability_search", "refine_search", "other"):
            intent = "other"

        patch = data.get("patch") if isinstance(data.get("patch"), dict) else {}
        for field in ("required_amenities", "preferred_amenities"):
            if field in patch:
                patch[field] = _canon_amen_list(patch.get(field))

        if "neighborhood" in patch and patch["neighborhood"]:
            hood = str(patch["neighborhood"]).strip()
            for allowed in ALLOWED_NEIGHBORHOODS:
                if hood.lower() == allowed.lower():
                    patch["neighborhood"] = allowed
                    break

        user_message = request.user_message or ""
        state = request.state or {}
        if re.search(r"\batlanta\b", user_message, re.IGNORECASE):
            patch.setdefault("city", DEMO_CITY)
            patch.setdefault("state", DEMO_STATE)

        month_year = _detect_month_year_from_text(user_message)
        if month_year:
            patch.setdefault("month", month_year["month"])
            patch.setdefault("year", month_year["year"])

        nights = _nights_from_text(user_message)
        if nights is not None:
            patch.setdefault("nights", nights)

        guests = _guests_from_text(user_message)
        if guests is not None:
            patch.setdefault("guests", guests)

        sort_by = _sort_from_text(user_message)
        if sort_by:
            patch.setdefault("sort_by", sort_by)

        if "check_in" not in patch:
            day = _day_of_month_from_text(user_message)
            if day is not None:
                month = int(patch.get("month") or state.get("month") or DEMO_MONTH)
                year = int(patch.get("year") or state.get("year") or DEMO_YEAR)
                if month == 6 and 1 <= day <= 30:
                    patch["check_in"] = f"{year:04d}-{month:02d}-{day:02d}"

        near_match = NEAR_RE.search(user_message)
        if near_match:
            poi = near_match.group(1).strip().rstrip(" .,!?:;")
            if poi:
                patch.setdefault("poi_query", poi)

        radius_match = RADIUS_RE.search(user_message)
        if radius_match:
            try:
                patch.setdefault("poi_radius_miles", float(radius_match.group(1)))
            except Exception:
                pass

        if BROADEN_RE.search(user_message):
            patch["poi_query"] = None
            patch["poi_resolved"] = False
            patch["poi_last_resolved_query"] = None
            patch["poi_lat"] = None
            patch["poi_lng"] = None
            patch["neighborhood"] = None

        confidence = data.get("confidence", 0.6)
        try:
            confidence = float(confidence)
        except Exception:
            confidence = 0.6
        confidence = max(0.0, min(1.0, confidence))

        if intent == "other":
            intent = _infer_intent(user_message, patch)

        return ExtractResponse(intent=intent, patch=patch, confidence=confidence)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {exc}")
