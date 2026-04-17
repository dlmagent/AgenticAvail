from __future__ import annotations

from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt
from typing import Dict, List, Literal, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field


POI_GEOCODE: Dict[str, tuple[float, float]] = {
    "georgia aquarium": (33.7634, -84.3951),
    "atlanta airport": (33.6407, -84.4277),
    "midtown atlanta": (33.7812, -84.3877),
    "downtown atlanta": (33.7537, -84.3863),
    "buckhead": (33.8476, -84.3673),
    "old fourth ward": (33.7669, -84.3643),
}


@dataclass(frozen=True)
class Property:
    hotel_id: str
    name: str
    neighborhood: str
    lat: float
    lng: float
    supplier: Literal["amadeus", "mock"] = "amadeus"
    supplier_code: str = ""


PROPERTIES: List[Property] = [
    Property("ATL-001", "Peachtree Plaza Inn (Fake)", "Downtown", 33.7573, -84.3873, "amadeus", "AMA-ATL-001"),
    Property("ATL-002", "Midtown Sky Suites (Fake)", "Midtown", 33.7815, -84.3880, "amadeus", "AMA-ATL-002"),
    Property("ATL-003", "Buckhead Luxe Hotel (Fake)", "Buckhead", 33.8480, -84.3670, "amadeus", "AMA-ATL-003"),
    Property("ATL-004", "Airport Jetway Lodge (Fake)", "Airport", 33.6405, -84.4275, "amadeus", "AMA-ATL-004"),
    Property("ATL-005", "Old Fourth Ward Boutique (Fake)", "O4W", 33.7672, -84.3640, "amadeus", "AMA-ATL-005"),
    Property("ATL-006", "Centennial Park Hotel (Fake)", "Downtown", 33.7605, -84.3932, "amadeus", "AMA-ATL-006"),
    Property("ATL-007", "Fox Theatre Residences (Fake)", "Midtown", 33.7726, -84.3859, "amadeus", "AMA-ATL-007"),
    Property("ATL-008", "Lenox Garden Hotel (Fake)", "Buckhead", 33.8458, -84.3628, "amadeus", "AMA-ATL-008"),
    Property("ATL-009", "Runway Commons Hotel (Fake)", "Airport", 33.6368, -84.4302, "amadeus", "AMA-ATL-009"),
    Property("ATL-010", "BeltLine Market Inn (Fake)", "O4W", 33.7699, -84.3587, "amadeus", "AMA-ATL-010"),
    Property("ATL-011", "Capitol View Suites (Fake)", "Downtown", 33.7489, -84.3917, "amadeus", "AMA-ATL-011"),
    Property("ATL-012", "Piedmont Park Retreat (Fake)", "Midtown", 33.7859, -84.3731, "amadeus", "AMA-ATL-012"),
]


def haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 3958.8
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    c = 2 * asin(sqrt(a))
    return radius * c


def best_neighborhood(candidates: List[Property]) -> Optional[str]:
    if not candidates:
        return None
    counts: Dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.neighborhood] = counts.get(candidate.neighborhood, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


class ResolveRequest(BaseModel):
    query: str = Field(..., examples=["Georgia Aquarium"])
    city: str = "Atlanta"
    state: str = "GA"
    radius_miles: Optional[float] = Field(default=3.0, ge=0.1, le=25.0)


class Candidate(BaseModel):
    hotel_id: str
    name: str
    neighborhood: str
    supplier: str
    supplier_code: str
    distance_miles: float


class ResolveResponse(BaseModel):
    query: str
    city: str
    state: str
    lat: float
    lng: float
    radius_miles: float
    recommended_neighborhood: Optional[str] = None
    candidates: List[Candidate] = Field(default_factory=list)


def resolve_property(request: ResolveRequest) -> ResolveResponse:
    query = (request.query or "").strip().lower()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    radius = request.radius_miles if request.radius_miles is not None else 3.0
    if query not in POI_GEOCODE:
        allowed = ", ".join(sorted(POI_GEOCODE.keys()))
        raise HTTPException(status_code=404, detail=f"Unknown place '{request.query}'. In this demo, try: {allowed}")

    lat, lng = POI_GEOCODE[query]
    hits: List[tuple[Property, float]] = []
    for property_item in PROPERTIES:
        distance = haversine_miles(lat, lng, property_item.lat, property_item.lng)
        if distance <= radius:
            hits.append((property_item, distance))

    hits.sort(key=lambda item: item[1])
    candidates = [
        Candidate(
            hotel_id=property_item.hotel_id,
            name=property_item.name,
            neighborhood=property_item.neighborhood,
            supplier=property_item.supplier,
            supplier_code=property_item.supplier_code,
            distance_miles=round(distance, 2),
        )
        for property_item, distance in hits
    ]

    return ResolveResponse(
        query=request.query,
        city=request.city,
        state=request.state,
        lat=lat,
        lng=lng,
        radius_miles=float(radius),
        recommended_neighborhood=best_neighborhood([property_item for property_item, _ in hits]),
        candidates=candidates,
    )
