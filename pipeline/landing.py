"""Module 6 — Compliant review landing page generator.

Compliance rules (hard requirements from spec + Google's review policy):
  * ONE outbound link to the business's Google review page for EVERY visitor.
  * NO sentiment gating / routing (no "were you happy?" fork).
  * NO star collection before the Google link.
  * NO incentives.

We render one static HTML page per business under landing/pages/r/{place_id}.html.
The public URL is: {LANDING_BASE_URL}/r/{place_id}.html
The Google "write a review" deep link uses the place_id.
"""
from __future__ import annotations

import html
import os
from typing import List

import config

GOOGLE_REVIEW_URL = "https://search.google.com/local/writereview?placeid={place_id}"

_PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Leave {name} a review</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
         margin: 0; display: grid; min-height: 100vh; place-items: center;
         background: #0f172a; color: #f8fafc; }}
  .card {{ max-width: 30rem; margin: 1.5rem; padding: 2rem; border-radius: 1rem;
          background: #1e293b; box-shadow: 0 10px 30px rgba(0,0,0,.35);
          text-align: center; }}
  .brand {{ font-size: .8rem; letter-spacing: .12em; text-transform: uppercase;
           color: #94a3b8; }}
  h1 {{ font-size: 1.5rem; margin: .5rem 0 1rem; }}
  p {{ line-height: 1.5; color: #cbd5e1; }}
  .cta {{ display: inline-block; margin-top: 1.5rem; padding: .9rem 1.6rem;
         border-radius: .6rem; background: #38bdf8; color: #0f172a;
         font-weight: 700; text-decoration: none; }}
  .cta:focus {{ outline: 3px solid #f8fafc; outline-offset: 2px; }}
  .foot {{ margin-top: 1.75rem; font-size: .75rem; color: #64748b; }}
</style>
</head>
<body>
  <main class="card">
    <div class="brand">{brand}</div>
    <h1>Thank you for visiting {name}!</h1>
    <p>Your feedback helps a local business grow. Tap below to share your
       honest experience on Google &mdash; it only takes a minute.</p>
    <a class="cta" href="{review_url}" rel="noopener">Write a Google review</a>
    <p class="foot">This page links every visitor directly to Google. We never
       filter reviews or offer incentives.</p>
  </main>
</body>
</html>
"""


def review_link(place_id: str) -> str:
    return GOOGLE_REVIEW_URL.format(place_id=place_id)


def landing_url(place_id: str) -> str:
    return f"{config.LANDING_BASE_URL}/r/{place_id}.html"


def _render(business: dict) -> str:
    place_id = business["place_id"]
    return _PAGE_TEMPLATE.format(
        name=html.escape(business.get("name", "this business")),
        brand=html.escape(config.BRAND_NAME),
        review_url=html.escape(review_link(place_id)),
    )


def generate(businesses: List[dict]) -> List[dict]:
    """Write a static landing page per business; annotate each with links."""
    os.makedirs(os.path.join(config.LANDING_DIR, "r"), exist_ok=True)
    count = 0
    for b in businesses:
        pid = b.get("place_id")
        if not pid:
            continue
        path = os.path.join(config.LANDING_DIR, "r", f"{pid}.html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(_render(b))
        b["review_link"] = review_link(pid)
        b["landing_url"] = landing_url(pid)
        b["landing_path"] = path
        count += 1

    print(f"✅ landing — {count} records")
    return businesses


if __name__ == "__main__":
    import json
    import sys

    data = json.load(sys.stdin)
    print(json.dumps(generate(data), indent=2))
