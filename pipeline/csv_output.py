"""Module 7 — CSV proof-of-work output (idempotent, dedupe on place_id).

Re-running the pipeline must NOT duplicate rows. We key on place_id: existing
rows are merged/updated in place, new rows appended.
"""
from __future__ import annotations

import csv
import os
from typing import Dict, List

import config

COLUMNS = [
    "place_id",
    "business_name",
    "category",
    "address",
    "phone",
    "website",
    "rating",
    "review_count",
    "owner_run_likelihood",
    "real_storefront",
    "willingness_to_pay",
    "priority_score",
    "postcard_pdf_path",
    "mail_proof_url",
    "review_link",
    "status",
]


def _to_row(b: dict) -> Dict[str, str]:
    return {
        "place_id": b.get("place_id", ""),
        "business_name": b.get("name", ""),
        "category": b.get("category", ""),
        "address": b.get("formatted_address", ""),
        "phone": b.get("phone", ""),
        "website": b.get("website", ""),
        "rating": b.get("rating", ""),
        "review_count": b.get("user_ratings_total", ""),
        "owner_run_likelihood": b.get("owner_run_likelihood", ""),
        "real_storefront": b.get("real_storefront", ""),
        "willingness_to_pay": b.get("willingness_to_pay", ""),
        "priority_score": b.get("priority_score", ""),
        "postcard_pdf_path": b.get("postcard_pdf_path", ""),
        "mail_proof_url": b.get("mail_proof_url", ""),
        "review_link": b.get("review_link", ""),
        "status": b.get("status", ""),
    }


def _read_existing(path: str) -> Dict[str, Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    if not os.path.exists(path):
        return rows
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            pid = row.get("place_id")
            if pid:
                rows[pid] = row
    return rows


def write(businesses: List[dict], path: str = None) -> str:
    path = path or config.RESULTS_CSV
    os.makedirs(os.path.dirname(path), exist_ok=True)

    existing = _read_existing(path)
    new_count = 0
    updated_count = 0
    for b in businesses:
        row = _to_row(b)
        pid = row["place_id"]
        if not pid:
            continue
        if pid in existing:
            updated_count += 1
        else:
            new_count += 1
        existing[pid] = row  # dedupe: last write wins for a given place_id

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in existing.values():
            writer.writerow({k: row.get(k, "") for k in COLUMNS})

    print(
        f"✅ csv_output — {len(existing)} records "
        f"({new_count} new, {updated_count} updated)"
    )
    return path


if __name__ == "__main__":
    import json
    import sys

    data = json.load(sys.stdin)
    write(data)
