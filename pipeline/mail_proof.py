"""Module 5 — Mail proof via Lob TEST mode ONLY.

Creates a postcard through Lob's **test** API to generate a proof PDF/URL.
Nothing is ever physically mailed.

HARD SAFETY RULES (spec):
  * Read LOB_TEST_KEY from env.
  * REFUSE any key that is not a Lob test key (must start with "test_").
    Live keys (`live_...`) are rejected outright — we never call live/prod
    mail endpoints.
  * If no key is configured, degrade to a LOCAL proof (reference the locally
    rendered postcard PDF) so the demo still runs, and flag it in status.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

import requests

import config

LOB_POSTCARDS_URL = "https://api.lob.com/v1/postcards"

# A Lob-provided deliverable US test address is used as the recipient so the
# test API accepts the request. This is a PROOF ONLY — nothing is mailed.
_TEST_TO = {
    "name": "Prospect Business (TEST)",
    "address_line1": "210 King St",
    "address_line2": "Suite 6100",
    "address_city": "San Francisco",
    "address_state": "CA",
    "address_zip": "94107",
    "address_country": "US",
}
_FROM = {
    "name": "CJ Studios",
    "address_line1": "185 Berry St",
    "address_line2": "Suite 6100",
    "address_city": "San Francisco",
    "address_state": "CA",
    "address_zip": "94107",
    "address_country": "US",
}


class LiveKeyRefused(RuntimeError):
    """Raised if a non-test (live) Lob key is supplied."""


def _validate_key(key: str) -> Optional[str]:
    """Return a usable test key, or None if unconfigured. Refuse live keys."""
    if not key:
        return None
    if key.startswith("live_"):
        raise LiveKeyRefused(
            "LOB_TEST_KEY looks like a LIVE key (starts with 'live_'). "
            "This demo only ever calls Lob TEST mode. Refusing to proceed."
        )
    if not key.startswith("test_"):
        raise LiveKeyRefused(
            "LOB_TEST_KEY must be a Lob TEST key (starts with 'test_'). "
            "Refusing to call Lob with an unrecognized key."
        )
    return key


def _back_html(business: dict) -> str:
    landing = business.get("landing_url", config.LANDING_BASE_URL)
    return (
        "<html><body style='font-family:Helvetica;margin:0;padding:0.4in;"
        "color:#0f172a;'>"
        f"<h2 style='margin:0 0 8px'>Grow your reviews with {config.BRAND_NAME}</h2>"
        f"<p style='color:#475569'>Scan the QR on the front, or visit "
        f"<b>{landing}</b> to start collecting more 5-star Google reviews.</p>"
        "<p style='font-size:9px;color:#94a3b8'>Sent as a TEST proof only. "
        "No mail dispatched.</p>"
        "</body></html>"
    )


def _create_lob_proof(business: dict, key: str) -> Tuple[str, str]:
    """POST the postcard to Lob TEST mode; return (proof_url, status)."""
    pdf_path = business.get("postcard_pdf_path")
    data = {
        "description": f"CJ Studios review outreach (TEST) - {business.get('name','')}",
        "size": "4x6",
        # Lob requires a mail use type; this is marketing outreach.
        "use_type": "marketing",
        "back": _back_html(business),
    }
    # to / from as bracketed form fields (Lob's form-encoding convention).
    for prefix, addr in (("to", _TEST_TO), ("from", _FROM)):
        for k, v in addr.items():
            data[f"{prefix}[{k}]"] = v

    files = None
    opened = None
    try:
        if pdf_path:
            opened = open(pdf_path, "rb")
            files = {"front": ("front.pdf", opened, "application/pdf")}
        else:
            data["front"] = (
                "<html><body><h1>CJ Studios</h1></body></html>"
            )
        resp = requests.post(
            LOB_POSTCARDS_URL,
            auth=(key, ""),  # HTTP basic: test key as username, empty password
            data=data,
            files=files,
            timeout=60,
        )
    finally:
        if opened:
            opened.close()

    if resp.status_code >= 400:
        return "", f"lob_error:{resp.status_code}"

    body = resp.json()
    # Sanity: Lob echoes the mode; guard against accidentally hitting live.
    if body.get("mode") == "live":
        raise LiveKeyRefused("Lob responded in LIVE mode; aborting.")
    proof_url = body.get("url", "")
    return proof_url, "mailed_test"


def generate(businesses: List[dict]) -> List[dict]:
    """Attach mail_proof_url + status to each business."""
    key = _validate_key(config.LOB_TEST_KEY)
    count = 0
    for b in businesses:
        if key:
            try:
                proof_url, status = _create_lob_proof(b, key)
            except LiveKeyRefused:
                raise
            except Exception as exc:  # noqa: BLE001
                proof_url, status = "", f"lob_exception:{type(exc).__name__}"
        else:
            # No test key -> local proof reference (still zero mail sent).
            pdf = b.get("postcard_pdf_path", "")
            proof_url = f"LOCAL-PROOF:{pdf}" if pdf else ""
            status = "local_proof_no_lob_key"

        b["mail_proof_url"] = proof_url
        b["status"] = status
        count += 1

    print(f"✅ mail_proof — {count} records")
    return businesses


if __name__ == "__main__":
    import json
    import sys

    data = json.load(sys.stdin)
    print(json.dumps(generate(data), indent=2))
