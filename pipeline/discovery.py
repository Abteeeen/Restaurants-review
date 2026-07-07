"""Module 1 — Discovery via the Google Places API.

Text Search -> Place Details for each result. API only; no HTML scraping.

Filter rule (spec):
    user_ratings_total < REVIEW_THRESHOLD AND business_status == OPERATIONAL

Safety: aborts and asks the operator before exceeding MAX_PLACES_REQUESTS
Places API calls in a single run.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass, field
from typing import List, Optional

import requests

import config

# Places API (New) — https://developers.google.com/maps/documentation/places/web-service
TEXTSEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# Field mask for Text Search: just enough to pre-filter + compute the
# competitor benchmark cheaply. Full contact fields are fetched via Place
# Details only for the results that pass the filter.
SEARCH_FIELDS = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.businessStatus",
        "places.userRatingCount",
        "nextPageToken",
    ]
)

# Field mask for Place Details (full contact record).
DETAIL_FIELDS = ",".join(
    [
        "id",
        "displayName",
        "formattedAddress",
        "nationalPhoneNumber",
        "websiteUri",
        "rating",
        "userRatingCount",
        "businessStatus",
        "types",
        "googleMapsUri",
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


def _text_search(query: str, budget: _Budget) -> List[dict]:
    """Return raw Text Search results (New Places API), following pages."""
    key = _require_key()
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": SEARCH_FIELDS,
    }
    results: List[dict] = []
    body = {"textQuery": query}
    page = 0
    while True:
        budget.spend(1)
        resp = requests.post(TEXTSEARCH_URL, json=body, headers=headers, timeout=30)
        if resp.status_code >= 400:
            msg = ""
            try:
                msg = resp.json().get("error", {}).get("message", "")
            except Exception:  # noqa: BLE001
                msg = resp.text[:200]
            raise RuntimeError(f"Places Text Search error {resp.status_code}: {msg}")
        data = resp.json()
        results.extend(data.get("places", []))
        token = data.get("nextPageToken")
        page += 1
        # Cap paging at 3 pages and respect the budget.
        if not token or page >= 3 or budget.count >= budget.limit:
            break
        body = {"textQuery": query, "pageToken": token}
    return results


def _place_details(place_id: str, budget: _Budget) -> Optional[dict]:
    key = _require_key()
    budget.spend(1)
    headers = {"X-Goog-Api-Key": key, "X-Goog-FieldMask": DETAIL_FIELDS}
    resp = requests.get(
        DETAILS_URL.format(place_id=place_id), headers=headers, timeout=30
    )
    if resp.status_code >= 400:
        return None
    return resp.json()


def discover(
    category: str,
    location: str,
    radius: int = None,
    review_threshold: int = None,
    max_requests: int = None,
    on_budget_exceeded=None,
    stats: dict = None,
) -> List[dict]:
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

    # `radius` is retained for CLI compatibility; the New Places API text
    # query is geo-scoped by the location string in `query`.
    _ = radius

    try:
        raw_results = _text_search(query, budget)
    except PlacesBudgetExceeded as exc:
        if on_budget_exceeded:
            on_budget_exceeded(exc, budget)
            return []
        raise

    qualified: List[Business] = []
    seen = set()
    max_reviews_seen = 0
    for r in raw_results:
        pid = r.get("id")
        if not pid or pid in seen:
            continue
        seen.add(pid)

        status = r.get("businessStatus", "")
        reviews = int(r.get("userRatingCount", 0) or 0)

        # Benchmark: highest review count of any OPERATIONAL business seen.
        if status == "OPERATIONAL":
            max_reviews_seen = max(max_reviews_seen, reviews)

        # Spec filter: low review count AND operational (pre-filtered from the
        # search result so we only spend Place Details calls on real prospects).
        if status != "OPERATIONAL" or reviews >= review_threshold:
            continue

        try:
            detail = _place_details(pid, budget)
        except PlacesBudgetExceeded as exc:
            if on_budget_exceeded:
                on_budget_exceeded(exc, budget)
                break
            raise
        if not detail:
            continue

        reviews = int(detail.get("userRatingCount", 0) or 0)
        status = detail.get("businessStatus", status)

        qualified.append(
            Business(
                place_id=detail.get("id", pid),
                name=(detail.get("displayName") or {}).get("text", ""),
                category=category,
                formatted_address=detail.get("formattedAddress", ""),
                phone=detail.get("nationalPhoneNumber", ""),
                website=detail.get("websiteUri", ""),
                rating=detail.get("rating"),
                user_ratings_total=reviews,
                business_status=status,
                google_maps_url=detail.get("googleMapsUri", ""),
                types=detail.get("types", []) or [],
            )
        )

    if stats is not None:
        stats["max_reviews_seen"] = max_reviews_seen
        stats["places_requests_used"] = budget.count

    print(f"✅ discovery — {len(qualified)} records")
    # Downstream modules consume plain dicts (b.get(...)), so hand off dicts.
    return [b.as_dict() for b in qualified]


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
    print(json.dumps(biz, indent=2))
