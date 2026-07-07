"""Central configuration for the CJ Studios review-outreach demo pipeline.

Every secret is read from the environment. Nothing is hardcoded and nothing
sensitive is ever printed. Values here are plain (non-secret) tuning knobs.
"""
import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv optional at runtime
    pass


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- Secrets (read lazily by the modules that need them) ---
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "google/gemini-2.5-flash")
LOB_TEST_KEY = os.environ.get("LOB_TEST_KEY", "")

# --- Non-secret tuning ---
LANDING_BASE_URL = os.environ.get(
    "LANDING_BASE_URL", "https://cjstudios.example.com"
).rstrip("/")
REVIEW_THRESHOLD = _int_env("REVIEW_THRESHOLD", 20)
SEARCH_RADIUS_METERS = _int_env("SEARCH_RADIUS_METERS", 8000)

# --- Safety guardrails (spec constraints) ---
MAX_PLACES_REQUESTS = 100  # stop-and-ask threshold for Places API calls

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
POSTCARD_DIR = os.path.join(OUTPUT_DIR, "postcards")
LANDING_DIR = os.path.join(BASE_DIR, "landing", "pages")
RESULTS_CSV = os.path.join(OUTPUT_DIR, "results.csv")

# --- Willingness-to-pay weights used by the deterministic ranker ---
WILLINGNESS_WEIGHTS = {"low": 0.4, "med": 0.7, "high": 1.0}

# --- Branding ---
BRAND_NAME = "CJ Studios"
BRAND_TAGLINE = "Local reviews, done right."
