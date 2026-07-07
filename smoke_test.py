#!/usr/bin/env python3
"""Offline smoke test: exercises qualification -> csv without any live API.

Discovery (module 1) requires GOOGLE_PLACES_API_KEY and is covered by its own
standalone entrypoint. This test drives modules 2-7 with fixture businesses so
the full downstream pipeline is verified end to end (heuristic qualification,
ranking, landing pages, postcard PDFs, local mail proof, idempotent CSV).
"""
import csv
import os

from pipeline import csv_output, landing, mail_proof, postcard, qualification, ranking

FIXTURES = [
    {
        "place_id": "TEST_place_bright_smile",
        "name": "Bright Smile Family Dental",
        "category": "dentist",
        "formatted_address": "12 Example St, Brisbane QLD 4000",
        "phone": "+61 7 1234 5678",
        "website": "",
        "rating": 4.9,
        "user_ratings_total": 4,
        "business_status": "OPERATIONAL",
        "types": ["dentist", "health"],
    },
    {
        "place_id": "TEST_place_river_cafe",
        "name": "River Bend Cafe",
        "category": "dentist",  # deliberately mismatched to test priors
        "formatted_address": "9 Sample Rd, Brisbane QLD 4000",
        "phone": "+61 7 8765 4321",
        "website": "https://riverbendcafe.example.com",
        "rating": 4.2,
        "user_ratings_total": 15,
        "business_status": "OPERATIONAL",
        "types": ["cafe", "food"],
    },
]


def main() -> int:
    businesses = [dict(f) for f in FIXTURES]

    businesses = qualification.qualify(businesses)
    businesses = ranking.rank(businesses, review_threshold=20)
    businesses = landing.generate(businesses)
    businesses = postcard.generate(businesses, benchmark=180)
    businesses = mail_proof.generate(businesses)
    path = csv_output.write(businesses)

    # Assertions
    assert businesses[0]["priority_score"] >= businesses[-1]["priority_score"], \
        "ranking not descending"
    for b in businesses:
        assert os.path.exists(b["postcard_pdf_path"]), "postcard PDF missing"
        assert os.path.exists(b["landing_path"]), "landing page missing"
        assert "writereview?placeid=" in b["review_link"], "bad review link"
        assert b["status"], "missing status"

    # Idempotency: re-run must not duplicate rows.
    n_before = _row_count(path)
    csv_output.write([dict(f) for f in FIXTURES] and businesses)
    n_after = _row_count(path)
    assert n_before == n_after == len(FIXTURES), \
        f"dedupe failed: {n_before} -> {n_after}"

    print("\n🎉 smoke test passed — all downstream modules verified.")
    print(f"   top prospect: {businesses[0]['name']} "
          f"(score {businesses[0]['priority_score']})")
    return 0


def _row_count(path: str) -> int:
    with open(path, newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.DictReader(fh))


if __name__ == "__main__":
    raise SystemExit(main())
