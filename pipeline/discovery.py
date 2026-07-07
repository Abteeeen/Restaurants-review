"""Module 1 — Discovery via the Google Places API.

Text Search -> Place Details for each result. API only; no HTML scraping.

Filter rule (spec):
    user_ratings_total < REVIEW_THRESHOLD AND business_status == OPERATIONAL

Safety: aborts and asks the operator before exceeding MAX_PLACES_REQUESTS
Places API calls in a single run.
"""
from __future__ import annotations

import sys
import time
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import requests

import config

TEXTSEARCH_URL = "https://maps.googleapis.com/maps/api/place/textsearch/json"
DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"

DETAIL_FIELDS = ",".join(
    [
        "name",
        "formatted_address",
        "formatted_phone_number",
        "website",
        "rating",
        "user_ratings_total",
        "business_status",
        "place_id",
        "types",
        "url",
    ]
)


@dataclass
class Business:
    place_id: str
    name: str
    category: str
    formatted_address: str = ""
    phone: str = ""
    website: str = ""
    rating: Optional[float] = None
    user_ratings_total: int = 0
    business_status: str = ""
    google_maps_url: str = ""
    types: List[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


class PlacesBudgetExceeded(RuntimeError):
    """Raised when a run would exceed the Places API request budget."""


class _Budget:
    """Tracks Places API request count against the stop-and-ask threshold."""

    def __init__(self, limit: int):
        self.limit = limit
        self.count = 0

    def spend(self, n: int = 1) -> None:
        if self.count + n > self.limit:
            raise PlacesBudgetExceeded(
                f"Would exceed the {self.limit}-request Places budget "
                f"(already used {self.count}). Per spec, stopping to ask before "
                f"making more Places API requests."
            )
        self.count += n


def _require_key() -> str:
    if not config.GOOGLE_PLACES_API_KEY:
        raise RuntimeError(
            "GOOGLE_PLACES_API_KEY is not set. Export it in your environment "
            "(see .env.example)."
        )
    return config.GOOGLE_PLACES_API_KEY


def _text_search(query: str, radius: int, budget: _Budget) -> List[dict]:
    """Return raw Text Search results, following up to a couple of pages."""
    key = _require_key()
    results: List[dict] = []
    params = {"query": query, "radius": radius, "key": key}
    page = 0
    while True:
        budget.spend(1)
        resp = requests.get(TEXTSEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        status = data.get("status")
        if status not in ("OK", "ZERO_RESULTS"):
            raise RuntimeError(
                f"Places Text Search error: {status} "
                f"{data.get('error_message', '')}".strip()
            )
        results.extend(data.get("results", []))
        token = data.get("next_page_token")
        page += 1
        # Cap paging at 3 pages (Google's max) and respect the budget.
        if not token or page >= 3 or budget.count >= budget.limit:
            break
        # next_page_token needs a short delay before it becomes valid.
        time.sleep(2)
        params = {"pagetoken": token, "key": key}
    return results


def _place_details(place_id: str, budget: _Budget) -> Optional[dict]:
    key = _require_key()
    budget.spend(1)
    resp = requests.get(
        DETAILS_URL,
        params={"place_id": place_id, "fields": DETAIL_FIELDS, "key": key},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "OK":
        return None
    return data.get("result")


def discover(
    category: str,
    location: str,
    radius: int = None,
    review_threshold: int = None,
    max_requests: int = None,
    on_budget_exceeded=None,
    stats: dict = None,
) -> List[Business]:
    """Discover low-review, operational businesses for a category + location.

    Returns a list of Business records that pass the spec filter. Raises
    PlacesBudgetExceeded (unless `on_budget_exceeded` handles it) if the run
    would cross the Places request budget.

    If `stats` (a dict) is provided, it is populated with run stats including
    `max_reviews_seen` — the highest review count of any OPERATIONAL business
    in the area, used as the postcard "top competitor" benchmark.
    """
    radius = radius if radius is not None else config.SEARCH_RADIUS_METERS
    review_threshold = (
        review_threshold if review_threshold is not None else config.REVIEW_THRESHOLD
    )
    max_requests = max_requests if max_requests is not None else config.MAX_PLACES_REQUESTS

    budget = _Budget(max_requests)
    query = f"{category} in {location}"

    try:
        raw_results = _text_search(query, radius, budget)
    except PlacesBudgetExceeded as exc:
        if on_budget_exceeded:
            on_budget_exceeded(exc, budget)
            return []
        raise

    qualified: List[Business] = []
    seen = set()
    max_reviews_seen = 0
    for r in raw_results:
        pid = r.get("place_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        try:
            detail = _place_details(pid, budget)
        except PlacesBudgetExceeded as exc:
            if on_budget_exceeded:
                on_budget_exceeded(exc, budget)
                break
            raise
        if not detail:
            continue

        status = detail.get("business_status", "")
        reviews = int(detail.get("user_ratings_total", 0) or 0)

        if status == "OPERATIONAL":
            max_reviews_seen = max(max_reviews_seen, reviews)

        # Spec filter: low review count AND operational.
        if status != "OPERATIONAL":
            continue
        if reviews >= review_threshold:
            continue

        qualified.append(
            Business(
                place_id=pid,
                name=detail.get("name", ""),
                category=category,
                formatted_address=detail.get("formatted_address", ""),
                phone=detail.get("formatted_phone_number", ""),
                website=detail.get("website", ""),
                rating=detail.get("rating"),
                user_ratings_total=reviews,
                business_status=status,
                google_maps_url=detail.get("url", ""),
                types=detail.get("types", []) or [],
            )
        )

    if stats is not None:
        stats["max_reviews_seen"] = max_reviews_seen
        stats["places_requests_used"] = budget.count

    print(f"✅ discovery — {len(qualified)} records")
    return qualified


if __name__ == "__main__":
    import argparse
    import json

    ap = argparse.ArgumentParser(description="Discovery module (standalone)")
    ap.add_argument("--category", required=True)
    ap.add_argument("--location", required=True)
    ap.add_argument("--radius", type=int, default=None)
    args = ap.parse_args()

    def _stop(exc, budget):
        print(f"\n⛔ {exc}", file=sys.stderr)
        sys.exit(2)

    biz = discover(
        args.category, args.location, radius=args.radius, on_budget_exceeded=_stop
    )
    print(json.dumps([b.as_dict() for b in biz], indent=2))
