"""Module 3 — Deterministic ranking (pure code, no LLM).

priority_score =
      normalized(REVIEW_THRESHOLD - user_ratings_total)
    * owner_run_likelihood
    * willingness_to_pay_weight
    * (1.2 if no website else 1.0)

Sorted descending => who to pitch first.
"""
from __future__ import annotations

from typing import List

import config


def _review_gap_norm(reviews: int, threshold: int) -> float:
    """Normalize (threshold - reviews) into [0, 1].

    A business with 0 reviews scores 1.0; one at the threshold scores 0.0.
    """
    if threshold <= 0:
        return 0.0
    gap = threshold - int(reviews or 0)
    gap = max(0, min(threshold, gap))
    return gap / threshold


def rank(businesses: List[dict], review_threshold: int = None) -> List[dict]:
    threshold = (
        review_threshold if review_threshold is not None else config.REVIEW_THRESHOLD
    )
    for b in businesses:
        gap = _review_gap_norm(b.get("user_ratings_total", 0), threshold)
        owner = float(b.get("owner_run_likelihood", 0.0) or 0.0)
        wtp_weight = config.WILLINGNESS_WEIGHTS.get(
            b.get("willingness_to_pay", "med"), 0.7
        )
        no_website_boost = 1.2 if not b.get("website") else 1.0

        score = gap * owner * wtp_weight * no_website_boost
        b["priority_score"] = round(score, 4)

    ranked = sorted(
        businesses, key=lambda x: x.get("priority_score", 0.0), reverse=True
    )
    print(f"✅ ranking — {len(ranked)} records")
    return ranked


if __name__ == "__main__":
    import json
    import sys

    data = json.load(sys.stdin)
    print(json.dumps(rank(data), indent=2))
