from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from fastapi import HTTPException
from openai import OpenAI
from pydantic import BaseModel, Field


MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1")
SYSTEM_PROMPT = """You are the Results Explainer Agent for a hotel-search demo.

You are given:
- the user's original message
- the current session state
- a structured search_response from the Availability Agent (search_response.matches)

Rules:
- You MUST NOT invent hotels, amenities, prices, totals, or availability.
- You MUST choose hotels ONLY from search_response.matches[*].hotel_id.
- If there are matches, select up to 5 hotel IDs (best aligned to the user intent and sort_by).
- If there are no matches, return an empty list of IDs.
- Keep output concise and demo-friendly.

Output MUST be valid JSON ONLY with:
- narrative: string
- top_hotel_ids: array of strings (hotel_id values from matches)
- suggested_refinements: array of strings
- followup_question: string
"""


class ExplainRequest(BaseModel):
    session_id: str
    user_message: str
    state: Dict[str, Any]
    search_response: Dict[str, Any]


class TopHotel(BaseModel):
    hotel_id: str
    name: str
    neighborhood: str
    stars: float
    amenities: List[str] = Field(default_factory=list)
    min_available_rooms_across_stay: int
    avg_nightly_rate_usd: float
    total_usd: float
    currency: str = "USD"
    preferred_matched: List[str] = Field(default_factory=list)
    matched_required_amenities: List[str] = Field(default_factory=list)
    distance_to_poi_miles: float | None = None


class ExplainResponse(BaseModel):
    narrative: str
    top_hotels: List[TopHotel] = Field(default_factory=list)
    suggested_refinements: List[str] = Field(default_factory=list)
    followup_question: str


def _canon_list(values: Any) -> List[str]:
    if not values:
        return []
    if not isinstance(values, list):
        values = [values]
    output: List[str] = []
    for value in values:
        text = str(value).strip().lower()
        if text and text not in output:
            output.append(text)
    return output


def explain_results(request: ExplainRequest) -> ExplainResponse:
    try:
        search_response = request.search_response or {}
        matches = search_response.get("matches") if isinstance(search_response, dict) else None
        if not isinstance(matches, list):
            matches = []

        if not matches:
            return ExplainResponse(
                narrative="I didn't find any matching hotels for those dates and filters.",
                top_hotels=[],
                suggested_refinements=[
                    "Relax required amenities (must-haves)",
                    "Try a different neighborhood",
                    "Increase max nightly or total budget",
                    "Shift dates within June 2026",
                ],
                followup_question="Want to relax amenities, change dates, or set a max nightly/total budget?",
            )

        match_by_id: Dict[str, Dict[str, Any]] = {}
        ordered_ids: List[str] = []
        for match in matches:
            if isinstance(match, dict) and match.get("hotel_id"):
                hotel_id = str(match["hotel_id"])
                match_by_id[hotel_id] = match
                ordered_ids.append(hotel_id)

        hotels_for_selection = []
        for hotel_id in ordered_ids:
            match = match_by_id[hotel_id]
            hotels_for_selection.append(
                {
                    "hotel_id": match.get("hotel_id"),
                    "name": match.get("name"),
                    "neighborhood": match.get("neighborhood"),
                    "stars": match.get("stars"),
                    "avg_nightly_rate_usd": match.get("avg_nightly_rate_usd"),
                    "total_usd": match.get("total_usd"),
                    "preferred_matched": match.get("preferred_matched"),
                    "min_available_rooms_across_stay": match.get("min_available_rooms_across_stay"),
                }
            )

        payload = {
            "user_message": request.user_message,
            "state": request.state,
            "search_response_summary": {
                "match_count": len(ordered_ids),
                "hotel_ids": ordered_ids,
                "sort_by": (search_response.get("query_echo") or {}).get("sort_by")
                if isinstance(search_response.get("query_echo"), dict)
                else None,
            },
            "hotels": hotels_for_selection,
        }

        client = OpenAI()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, default=str)},
            ],
        )
        text = response.choices[0].message.content or ""
        try:
            data = json.loads(text)
        except Exception:
            data = {}

        top_ids = data.get("top_hotel_ids")
        if not isinstance(top_ids, list):
            top_ids = []
        top_ids = [str(item) for item in top_ids if str(item) in match_by_id][:5]
        if not top_ids:
            top_ids = ordered_ids[:5]

        required = _canon_list((request.state or {}).get("required_amenities"))
        top_hotels: List[TopHotel] = []
        for hotel_id in top_ids:
            hotel = dict(match_by_id[hotel_id])
            amenity_set = {str(amenity).lower() for amenity in (hotel.get("amenities") or [])}
            hotel["matched_required_amenities"] = [amenity for amenity in required if amenity in amenity_set]
            top_hotels.append(TopHotel(**hotel))

        narrative = str(data.get("narrative") or "").strip()
        if not narrative:
            narrative = f"Here are {len(top_hotels)} hotel options in Atlanta for your requested stay."

        suggested = data.get("suggested_refinements")
        suggested_refinements = [str(item) for item in suggested][:12] if isinstance(suggested, list) else []
        followup = str(data.get("followup_question") or "").strip()
        if not followup:
            followup = "Would you like to filter by amenities, neighborhood, or price range?"

        return ExplainResponse(
            narrative=narrative,
            top_hotels=top_hotels,
            suggested_refinements=suggested_refinements,
            followup_question=followup,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Explainer error: {exc}")
