#!/usr/bin/env python3
"""Local-business review-outreach pipeline (DEMO).

Orchestrates the seven modules end to end:

    discovery -> qualification -> ranking -> landing -> postcard
              -> mail_proof (Lob TEST) -> csv_output

DEMO SAFETY:
  * No real mail is ever sent (Lob TEST mode only; live keys refused).
  * No face generation, no fabricated imagery of real people.
  * Stops and asks before exceeding 100 Places API requests in one run.
  * Every secret comes from the environment.

Usage:
    python run.py --category "dentist" --location "Brisbane QLD"
"""
from __future__ import annotations

import argparse
import sys

import config
from pipeline import (
    csv_output,
    discovery,
    landing,
    mail_proof,
    qualification,
    ranking,
)


def _confirm_over_budget(exc, budget) -> None:
    """Called if discovery would exceed the Places request budget."""
    print(f"\n⛔ STOP: {exc}", file=sys.stderr)
    print(
        "Per spec, I will not exceed 100 Places API requests without your "
        "go-ahead. Re-run with --max-places-requests <N> to raise the cap, "
        "or narrow the search (smaller radius / more specific category).",
        file=sys.stderr,
    )
    sys.exit(3)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--category", required=True, help='e.g. "dentist"')
    ap.add_argument("--location", required=True, help='e.g. "Brisbane QLD"')
    ap.add_argument("--radius", type=int, default=None, help="meters")
    ap.add_argument(
        "--review-threshold", type=int, default=None,
        help=f"default {config.REVIEW_THRESHOLD}",
    )
    ap.add_argument(
        "--max-places-requests", type=int, default=None,
        help=f"Places API request cap (default {config.MAX_PLACES_REQUESTS})",
    )
    ap.add_argument(
        "--limit", type=int, default=None,
        help="only process the top-N ranked prospects (postcards/mail)",
    )
    args = ap.parse_args(argv)

    threshold = (
        args.review_threshold
        if args.review_threshold is not None
        else config.REVIEW_THRESHOLD
    )

    print(
        f"\n=== {config.BRAND_NAME} pipeline: {args.category} @ {args.location} ===\n"
    )

    # 1. DISCOVERY
    stats: dict = {}
    businesses = discovery.discover(
        category=args.category,
        location=args.location,
        radius=args.radius,
        review_threshold=threshold,
        max_requests=args.max_places_requests,
        on_budget_exceeded=_confirm_over_budget,
        stats=stats,
    )
    if not businesses:
        print("\nNo qualifying businesses found. Nothing further to do.")
        return 0

    # 2. QUALIFICATION (OpenRouter — no fallback; fails loudly per row)
    businesses = qualification.qualify(businesses)

    # 3. RANKING (deterministic)
    businesses = ranking.rank(businesses, review_threshold=threshold)

    # Rows whose live classification failed are never pitched or fabricated —
    # they flow straight to the CSV keeping status=QUALIFICATION_FAILED.
    qualified = [
        b for b in businesses
        if b.get("qualification_source") != qualification.SOURCE_FAILED
    ]
    failed = [
        b for b in businesses
        if b.get("qualification_source") == qualification.SOURCE_FAILED
    ]

    if args.limit is not None:
        qualified = qualified[: args.limit]

    # Benchmark for the postcard "top competitor" line.
    benchmark = max(stats.get("max_reviews_seen", 0), threshold * 3)

    # 6. LANDING PAGES (before postcards — QR points here)
    qualified = landing.generate(qualified)

    # 4. POSTCARDS
    qualified = postcard_generate(qualified, benchmark)

    # 5. MAIL PROOF (Lob TEST mode)
    qualified = mail_proof.generate(qualified)

    # 7. CSV OUTPUT (idempotent) — qualified + failed rows
    businesses = qualified + failed
    csv_path = csv_output.write(businesses)

    print("\n=== Summary ===")
    print(f"Prospects processed : {len(businesses)}")
    print(f"Qualified (pitched) : {len(qualified)}")
    print(f"Qualification failed: {len(failed)}")
    print(f"Places requests used: {stats.get('places_requests_used', '?')}")
    print(f"Competitor benchmark: {benchmark} reviews")
    print(f"Results CSV         : {csv_path}")
    print(f"Postcards           : {config.POSTCARD_DIR}/")
    print(f"Landing pages       : {config.LANDING_DIR}/r/")
    if qualified:
        top = qualified[0]
        print(
            f"Top prospect        : {top.get('name')} "
            f"(score {top.get('priority_score')})"
        )
    print("\nDEMO complete. Zero real mail sent. ✅")
    return 0


def postcard_generate(businesses, benchmark):
    # Imported here to keep the heavy reportlab import lazy.
    from pipeline import postcard

    return postcard.generate(businesses, benchmark=benchmark)


if __name__ == "__main__":
    raise SystemExit(main())
