from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from random import Random
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class Hotel:
    hotel_id: str
    name: str
    city: str
    state: str
    neighborhood: str
    stars: float
    base_rate_usd: float
    amenities: List[str]


HOTEL_CATALOG = [
    ("ATL-001", "Peachtree Plaza Inn (Fake)", "Atlanta", "GA", "Downtown", 4.2, 219.0, 18),
    ("ATL-002", "Midtown Sky Suites (Fake)", "Atlanta", "GA", "Midtown", 4.0, 249.0, 12),
    ("ATL-003", "Buckhead Luxe Hotel (Fake)", "Atlanta", "GA", "Buckhead", 4.6, 329.0, 10),
    ("ATL-004", "Airport Jetway Lodge (Fake)", "Atlanta", "GA", "Airport", 3.8, 159.0, 25),
    ("ATL-005", "Old Fourth Ward Boutique (Fake)", "Atlanta", "GA", "O4W", 4.4, 279.0, 8),
    ("ATL-006", "Centennial Park Hotel (Fake)", "Atlanta", "GA", "Downtown", 4.1, 209.0, 16),
    ("ATL-007", "Fox Theatre Residences (Fake)", "Atlanta", "GA", "Midtown", 4.3, 269.0, 11),
    ("ATL-008", "Lenox Garden Hotel (Fake)", "Atlanta", "GA", "Buckhead", 4.5, 309.0, 9),
    ("ATL-009", "Runway Commons Hotel (Fake)", "Atlanta", "GA", "Airport", 3.9, 169.0, 22),
    ("ATL-010", "BeltLine Market Inn (Fake)", "Atlanta", "GA", "O4W", 4.1, 229.0, 13),
    ("ATL-011", "Capitol View Suites (Fake)", "Atlanta", "GA", "Downtown", 3.7, 189.0, 20),
    ("ATL-012", "Piedmont Park Retreat (Fake)", "Atlanta", "GA", "Midtown", 4.7, 339.0, 7),
]

DEFAULT_AMENITIES = ["restaurant", "fitness facility"]
OPTIONAL_AMENITIES = ["spa", "swimming pool", "pet friendly"]
BASE_INVENTORY_BY_HOTEL = {hotel_id: base_inventory for hotel_id, *_rest, base_inventory in HOTEL_CATALOG}


def _amenities_for_hotel(hotel_id: str, stars: float, base_rate_usd: float) -> List[str]:
    amenities = set(DEFAULT_AMENITIES)

    # Higher-end properties skew toward spas, while pools and pet-friendly access
    # vary deterministically per hotel to keep the demo data stable.
    if stars >= 4.4:
        amenities.add("spa")
    elif Random(f"{hotel_id}:spa").random() >= 0.8:
        amenities.add("spa")

    if base_rate_usd <= 180 or Random(f"{hotel_id}:pool").random() >= 0.45:
        amenities.add("swimming pool")
    if Random(f"{hotel_id}:pet").random() >= 0.55:
        amenities.add("pet friendly")

    for amenity in OPTIONAL_AMENITIES:
        if amenity not in amenities and Random(f"{hotel_id}:{amenity}:bonus").random() >= 0.9:
            amenities.add(amenity)

    ordered_amenities = [amenity for amenity in DEFAULT_AMENITIES + OPTIONAL_AMENITIES if amenity in amenities]
    return ordered_amenities


def _daterange(start: date, end: date):
    current = start
    while current < end:
        yield current
        current += timedelta(days=1)


def build_in_memory_db() -> Tuple[List[Hotel], Dict[str, Dict[date, int]]]:
    hotels = [
        Hotel(
            hotel_id,
            name,
            city,
            state,
            neighborhood,
            stars,
            base_rate_usd,
            _amenities_for_hotel(hotel_id, stars, base_rate_usd),
        )
        for hotel_id, name, city, state, neighborhood, stars, base_rate_usd, _base_inventory in HOTEL_CATALOG
    ]

    start = date(2026, 6, 1)
    end = date(2026, 7, 1)
    availability: Dict[str, Dict[date, int]] = {}
    for hotel in hotels:
        availability[hotel.hotel_id] = {}
        for current in _daterange(start, end):
            base = BASE_INVENTORY_BY_HOTEL[hotel.hotel_id]
            is_weekend = current.weekday() in (4, 5)
            weekend_delta = -6 if is_weekend else 0
            event_delta = -7 if date(2026, 6, 14) <= current <= date(2026, 6, 17) else 0
            end_of_month_delta = -4 if current.day in (24, 25, 26) else 0
            availability[hotel.hotel_id][current] = max(0, base + weekend_delta + event_delta + end_of_month_delta)
    return hotels, availability
