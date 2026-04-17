from __future__ import annotations

from datetime import date, timedelta
from typing import List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field

from .availability_data import Hotel, build_in_memory_db
from .property_resolver import PROPERTIES, haversine_miles


HOTELS, AVAILABILITY = build_in_memory_db()
CANON_AMENITIES = {"spa", "restaurant", "swimming pool", "fitness facility", "pet friendly"}
SortBy = Literal["best_value", "lowest_total", "lowest_avg_nightly", "best_rating", "most_availability", "closest_to_poi"]
PROPERTY_COORDS = {property_item.hotel_id: (property_item.lat, property_item.lng) for property_item in PROPERTIES}


class SearchRequest(BaseModel):
    city: str
    state: Optional[str] = "GA"
    check_in: date
    check_out: date
    rooms: int = Field(default=1, ge=1, le=5)
    guests: int = Field(default=2, ge=1, le=10)
    neighborhood: Optional[str] = None
    required_amenities: Optional[List[str]] = None
    preferred_amenities: Optional[List[str]] = None
    max_nightly_rate_usd: Optional[float] = Field(default=None, ge=0)
    max_total_usd: Optional[float] = Field(default=None, ge=0)
    poi_lat: Optional[float] = None
    poi_lng: Optional[float] = None
    sort_by: Optional[SortBy] = "best_value"


class RateBreakdown(BaseModel):
    date: date
    nightly_rate_usd: float


class HotelResult(BaseModel):
    hotel_id: str
    name: str
    neighborhood: str
    stars: float
    amenities: List[str]
    min_available_rooms_across_stay: int
    avg_nightly_rate_usd: float
    total_usd: float
    currency: str = "USD"
    rate_breakdown: List[RateBreakdown]
    preferred_match_count: int = 0
    preferred_matched: List[str] = Field(default_factory=list)
    distance_to_poi_miles: Optional[float] = None


class SearchResponse(BaseModel):
    matches: List[HotelResult]
    query_echo: SearchRequest


def _stay_nights(check_in: date, check_out: date) -> List[date]:
    current = check_in
    nights: List[date] = []
    while current < check_out:
        nights.append(current)
        current += timedelta(days=1)
    return nights


def _nightly_rate(hotel: Hotel, night: date) -> float:
    rate = float(hotel.base_rate_usd)
    if night.weekday() in (4, 5):
        rate += 35.0
    if date(2026, 6, 14) <= night <= date(2026, 6, 17):
        rate += 45.0
    if night.day in (24, 25, 26):
        rate += 20.0
    return round(rate, 2)


def _canon_list(values: Optional[List[str]]) -> List[str]:
    if not values:
        return []
    items: List[str] = []
    for value in values:
        normalized = str(value).strip().lower()
        if normalized:
            items.append(normalized)
    seen = set()
    unique: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def search_hotels(request: SearchRequest) -> SearchResponse:
    if request.check_out <= request.check_in:
        raise HTTPException(status_code=400, detail="check_out must be after check_in")
    if request.city.lower() != "atlanta":
        raise HTTPException(status_code=400, detail="Demo supports Atlanta only.")
    if request.state and request.state.lower() not in ("ga", "georgia"):
        raise HTTPException(status_code=400, detail="Demo supports GA only.")
    if not (date(2026, 6, 1) <= request.check_in < date(2026, 7, 1)):
        raise HTTPException(status_code=400, detail="Demo data supports check_in in June 2026 only.")
    if not (date(2026, 6, 2) <= request.check_out <= date(2026, 7, 1)):
        raise HTTPException(status_code=400, detail="Demo data supports check_out in June 2026 only.")

    nights = _stay_nights(request.check_in, request.check_out)
    required = _canon_list(request.required_amenities)
    preferred = _canon_list(request.preferred_amenities)

    for amenity in required + preferred:
        if amenity not in CANON_AMENITIES:
            raise HTTPException(status_code=400, detail=f"Unsupported amenity: {amenity}.")

    results: List[HotelResult] = []
    for hotel in HOTELS:
        if request.neighborhood and hotel.neighborhood.lower() != request.neighborhood.lower():
            continue
        amenity_set = set(hotel.amenities)
        if required and not all(amenity in amenity_set for amenity in required):
            continue

        min_rooms = min(AVAILABILITY[hotel.hotel_id].get(night, 0) for night in nights)
        if min_rooms < request.rooms:
            continue

        breakdown = [RateBreakdown(date=night, nightly_rate_usd=_nightly_rate(hotel, night)) for night in nights]
        total = round(sum(item.nightly_rate_usd for item in breakdown) * request.rooms, 2)
        avg = round(sum(item.nightly_rate_usd for item in breakdown) / max(1, len(breakdown)), 2)

        if request.max_nightly_rate_usd is not None and avg > request.max_nightly_rate_usd:
            continue
        if request.max_total_usd is not None and total > request.max_total_usd:
            continue

        matched = [amenity for amenity in preferred if amenity in amenity_set]
        distance_to_poi_miles = None
        if request.poi_lat is not None and request.poi_lng is not None:
            coords = PROPERTY_COORDS.get(hotel.hotel_id)
            if coords:
                distance_to_poi_miles = round(haversine_miles(request.poi_lat, request.poi_lng, coords[0], coords[1]), 2)
        results.append(
            HotelResult(
                hotel_id=hotel.hotel_id,
                name=hotel.name,
                neighborhood=hotel.neighborhood,
                stars=hotel.stars,
                amenities=hotel.amenities,
                min_available_rooms_across_stay=min_rooms,
                avg_nightly_rate_usd=avg,
                total_usd=total,
                rate_breakdown=breakdown,
                preferred_match_count=len(matched),
                preferred_matched=matched,
                distance_to_poi_miles=distance_to_poi_miles,
            )
        )

    sort_by = request.sort_by or "best_value"
    if sort_by == "lowest_total":
        results.sort(key=lambda item: (item.total_usd, -item.stars, -item.preferred_match_count, -item.min_available_rooms_across_stay))
    elif sort_by == "lowest_avg_nightly":
        results.sort(key=lambda item: (item.avg_nightly_rate_usd, item.total_usd, -item.stars, -item.preferred_match_count))
    elif sort_by == "best_rating":
        results.sort(key=lambda item: (-item.stars, item.total_usd, -item.preferred_match_count))
    elif sort_by == "most_availability":
        results.sort(key=lambda item: (-item.min_available_rooms_across_stay, item.total_usd, -item.stars, -item.preferred_match_count))
    elif sort_by == "closest_to_poi":
        if request.poi_lat is None or request.poi_lng is None:
            raise HTTPException(status_code=400, detail="poi_lat and poi_lng are required when sort_by=closest_to_poi")
        results.sort(
            key=lambda item: (
                float("inf") if item.distance_to_poi_miles is None else item.distance_to_poi_miles,
                item.total_usd,
                -item.stars,
                -item.preferred_match_count,
            )
        )
    else:
        results.sort(key=lambda item: (-item.stars, -item.preferred_match_count, item.total_usd, -item.min_available_rooms_across_stay))

    return SearchResponse(matches=results, query_echo=request)
