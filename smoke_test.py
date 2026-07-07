#!/usr/bin/env python3
"""Offline smoke test: exercises qualification -> csv without live network.

Qualification (module 2) now calls OpenRouter with NO heuristic fallback, so
this test injects deterministic test doubles for the OpenRouter calls (this is
a test harness, not a production fallback) and verifies:
  * the happy path flows through ranking, landing, postcards, mail proof, CSV;
  * a row whose live classification fails is marked FAILED, is NOT fabricated,
    and still lands in the CSV with status=QUALIFICATION_FAILED;
  * the CSV carries the qualification_source column;
  * re-running is idempotent (dedupe on place_id).

Discovery (module 1) needs GOOGLE_PLACES_API_KEY and is covered by its own
standalone entrypoint.
"""
import csv
import os

from pipeline import (
    csv_output,
    landing,
    mail_proof,
    postcard,
    qualification,
    ranking,
)

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
        "category": "cafe",
        "formatted_address": "9 Sample Rd, Brisbane QLD 4000",
        "phone": "+61 7 8765 4321",
        "website": "https://riverbendcafe.example.com",
        "rating": 4.2,
        "user_ratings_total": 15,
        "business_status": "OPERATIONAL",
        "types": ["cafe", "food"],
    },
    {
        # This fixture's classification is made to fail deterministically.
        "place_id": "TEST_place_flaky",
        "name": "Flaky Endpoint Barbers",
        "category": "barber",
        "formatted_address": "1 Timeout Ln, Brisbane QLD 4000",
        "phone": "+61 7 0000 0000",
        "website": "",
        "rating": 4.0,
        "user_ratings_total": 8,
        "business_status": "OPERATIONAL",
        "types": ["hair_care"],
    },
]


def _install_test_doubles():
    """Replace the OpenRouter network calls with deterministic doubles."""
    qualification.verify_model_available = lambda *a, **k: None
    qualification.MAX_RETRIES = 1
    qualification.BACKOFF_BASE = 0.0

    def fake_classify_once(business, key):
        if "Flaky" in business.get("name", ""):
            raise RuntimeError("simulated OpenRouter timeout")
        wtp = "high" if business.get("category") == "dentist" else "low"
        return {
            "owner_run_likelihood": 0.8,
            "real_storefront": True,
            "willingness_to_pay": wtp,
        }

    qualification._classify_once = fake_classify_once
    # Ensure the config gate (requires a key) passes under the doubles.
    import config

    config.OPENROUTER_API_KEY = config.OPENROUTER_API_KEY or "test-double-key"


def main() -> int:
    _install_test_doubles()

    businesses = [dict(f) for f in FIXTURES]

    businesses = qualification.qualify(businesses)
    businesses = ranking.rank(businesses)

    qualified = [
        b for b in businesses
        if b.get("qualification_source") != qualification.SOURCE_FAILED
    ]
    failed = [
        b for b in businesses
        if b.get("qualification_source") == qualification.SOURCE_FAILED
    ]

    # Exactly one fixture is engineered to fail.
    assert len(failed) == 1 and failed[0]["place_id"] == "TEST_place_flaky", failed
    assert failed[0]["status"] == "QUALIFICATION_FAILED"
    assert failed[0]["owner_run_likelihood"] is None, "must not fabricate on failure"

    qualified = landing.generate(qualified)
    qualified = postcard.generate(qualified, benchmark=180)
    qualified = mail_proof.generate(qualified)

    all_rows = qualified + failed
    path = csv_output.write(all_rows)

    # Assertions on the happy path
    assert qualified[0]["priority_score"] >= qualified[-1]["priority_score"], \
        "ranking not descending"
    for b in qualified:
        assert b["qualification_source"] == "openrouter:gemini-2.5-flash", b
        assert os.path.exists(b["postcard_pdf_path"]), "postcard PDF missing"
        assert os.path.exists(b["landing_path"]), "landing page missing"
        assert "writereview?placeid=" in b["review_link"], "bad review link"

    # CSV carries qualification_source, and the failed row survives as FAILED.
    with open(path, newline="", encoding="utf-8") as fh:
        by_id = {r["place_id"]: r for r in csv.DictReader(fh)}
    assert "qualification_source" in next(iter(by_id.values())), "column missing"
    assert by_id["TEST_place_flaky"]["qualification_source"] == "FAILED"
    assert by_id["TEST_place_flaky"]["status"] == "QUALIFICATION_FAILED"
    assert by_id["TEST_place_bright_smile"]["qualification_source"] == \
        "openrouter:gemini-2.5-flash"

    # Idempotency: re-run must not duplicate rows.
    n_before = len(by_id)
    csv_output.write(all_rows)
    with open(path, newline="", encoding="utf-8") as fh:
        n_after = sum(1 for _ in csv.DictReader(fh))
    assert n_before == n_after == len(FIXTURES), \
        f"dedupe failed: {n_before} -> {n_after}"

    print("\n🎉 smoke test passed — OpenRouter contract + downstream verified.")
    print(f"   pitched: {len(qualified)}  failed: {len(failed)}")
    print(f"   top prospect: {qualified[0]['name']} "
          f"(score {qualified[0]['priority_score']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
