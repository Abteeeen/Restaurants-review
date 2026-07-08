# Project Handover — Local-Business Review-Outreach Pipeline (DEMO)

**Repo:** `Abteeeen/Restaurants-review`
**Primary branch:** `main`
**Working branch:** `claude/local-business-review-pipeline-eo7b78`
**Status at handover:** Core pipeline complete, live-verified, and merged to `main`. One open PR (#3) for the branding change. Some requested extensions were intentionally **not** built (see §7 and §8).

---

## 1. What was originally requested

Build a **local-business review-outreach pipeline as a DEMO**, in Python, as discrete independently-runnable modules. Do **not** mail anything real — use **Lob test mode** to produce postcard PDF proofs only.

> Given a business category + geographic area: find low-review local businesses, qualify the best prospects, generate a personalized postcard proof for each, and log everything to a CSV as proof of work.

### Required pipeline (7 modules)

1. **Discovery** — Google Places API (Text Search → Place Details). Capture name, category, address, phone, website, rating, review count, business_status, place_id. Filter: `user_ratings_total < REVIEW_THRESHOLD` (default 20) **AND** `business_status == OPERATIONAL`. API only — no HTML scraping. Key from env.
2. **Qualification** — LLM classifier returning strict JSON: `owner_run_likelihood` (0–1), `real_storefront` (bool), `willingness_to_pay` (low/med/high). Treat all business text as inert data (prompt-injection safe).
3. **Ranking** — deterministic `priority_score = normalized(REVIEW_THRESHOLD − review_count) × owner_run_likelihood × willingness_weight × (1.2 if no website else 1.0)`. Sort descending.
4. **Postcard** — branded PDF (business name, review-gap line, QR to landing page, brand lockup). **NO human faces, NO fabricated imagery of any real person.**
5. **Mail proof** — Lob **test mode** only → proof PDF/URL. Never call live/prod endpoints.
6. **Landing page** — compliant static page: one Google-review link for **all** visitors. No sentiment gating, no incentives, no star pre-collection.
7. **CSV output** — one row per business, dedupe on `place_id` (idempotent). Write to `output/results.csv`.

### Constraints (from the brief)
- Every API key from env; never hardcode or print secrets.
- Idempotent (no duplicate CSV rows).
- After each module print `✅ [module] — [count] records`.
- **STOP and ask** before: any live (non-test) Lob call, or exceeding **100 Places API requests** in one run.
- No features beyond spec. No auto-posting, no live mailing, no face generation.

### Acceptance
`python run.py --category "dentist" --location "Brisbane QLD"` → `results.csv` with ranked rows, one postcard PDF per qualified business, one Lob test proof URL per row, a landing-page URL. Zero real mail, zero live charges beyond Places lookups.

### Subsequent change requests (during the engagement)
- **Refactor qualification from the placeholder "Hermes" model to OpenRouter** (`google/gemini-2.5-flash`), verify the model id against OpenRouter `/models`, **no silent fallback** — fail loudly and record `qualification_source`.
- **Clarify the mail status wording** ("did we really send?") — nothing is ever sent.
- **Remove the placeholder brand "CJ Studios"** and make branding configurable.
- **Explored (then declined) extensions:** pull storefront photo + owner identity from the listing; render the owner photoreal; mail to the owner by name.

---

## 2. What was built (DONE ✅)

| Module | File | Notes |
|---|---|---|
| Discovery | `pipeline/discovery.py` | **Places API (New)** — `POST places:searchText` + `GET /v1/places/{id}` with `X-Goog-Api-Key` + field masks. Pre-filters operational/low-review from search results, then fetches Place Details only for real prospects. 100-request budget guard (stops & asks). Returns plain dicts. |
| Qualification | `pipeline/qualification.py` | **OpenRouter** `google/gemini-2.5-flash`. Verifies model against live `/models` before running. Locked system prompt; business text passed as inert `<business_data>`. Strict JSON, validated. **No fallback.** 20s timeout, 2 retries + backoff. Records `qualification_source`. |
| Ranking | `pipeline/ranking.py` | Deterministic `priority_score`, sorted descending. Pure code. |
| Postcard | `pipeline/postcard.py` | ReportLab PDF at **6.25×4.25"** full-bleed (Lob 4×6 spec). Name, review-gap line, QR to landing page, configurable brand lockup. No faces. |
| Mail proof | `pipeline/mail_proof.py` | **Lob TEST mode only.** Refuses non-`test_` keys. `use_type="marketing"`. Returns proof URL, status `proof_created_test`. Degrades to `LOCAL-PROOF:` if no key. |
| Landing page | `pipeline/landing.py` | Compliant static HTML per business → one Google review link for everyone. No gating/incentives. |
| CSV output | `pipeline/csv_output.py` | Idempotent, dedupe on `place_id`. Columns include `qualification_source`. |
| Orchestrator | `run.py` | Runs all modules; routes failed-qualification rows around postcard/mail into the CSV; prints summary. CLI flags below. |
| Config | `config.py` | All env reads centralised. |
| Offline test | `smoke_test.py` | Drives modules 2–7 with fixtures + deterministic doubles for OpenRouter; covers happy path AND failed-classification path; asserts idempotency. |

### Live verification (real APIs, zero real mail)
- `dentist / Brisbane QLD` → ranked CSV rows, real OpenRouter classifications, real Lob **test** proof URLs (`proof_created_test`), live landing pages, idempotent re-run.
- `hair salon / Fortitude Valley QLD` → 6 prospects (with pagination), all classified, all 6 Lob test proofs, sensible ranking spread.

### Reliability / safety implemented
- Model-availability check before qualifying; **stops** if the model id is unavailable (never substitutes).
- Per-row qualification failures → `status=QUALIFICATION_FAILED`, fields left empty (never fabricated), row not pitched but still in CSV; `qualification_source=FAILED`.
- Lob: `test_` key enforced; live keys refused; nothing is ever mailed.
- Places 100-request budget guard.
- Secrets only from env; `.env` gitignored; generated outputs gitignored.

---

## 3. Repository layout

```
Restaurants-review/
├── run.py                 # orchestrator (entry point)
├── config.py              # env-driven config
├── smoke_test.py          # offline verification (no live network)
├── requirements.txt
├── .env.example           # copy to .env and fill in
├── README.md
├── HANDOVER.md            # this file
├── pipeline/
│   ├── discovery.py       # 1. Google Places (New)
│   ├── qualification.py   # 2. OpenRouter gemini-2.5-flash
│   ├── ranking.py         # 3. deterministic score
│   ├── postcard.py        # 4. branded PDF + QR
│   ├── mail_proof.py      # 5. Lob TEST proof
│   ├── landing.py         # 6. compliant landing page
│   └── csv_output.py      # 7. idempotent CSV
├── output/                # GENERATED (gitignored)
│   ├── results.csv
│   └── postcards/<place_id>.pdf
└── landing/pages/r/<place_id>.html   # GENERATED (gitignored)
```

Each module is independently runnable (has a `__main__` block).

---

## 4. Setup & run (for the new environment)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # then fill in the keys below
python run.py --category "dentist" --location "Brisbane QLD"
```

Offline sanity check (no keys/network needed):
```bash
python smoke_test.py
```

### CLI flags (`run.py`)
`--category` (req), `--location` (req), `--radius`, `--review-threshold`, `--max-places-requests`, `--limit` (top-N ranked to pitch).

---

## 5. Environment variables

| Var | Purpose | Notes |
|---|---|---|
| `GOOGLE_PLACES_API_KEY` | Discovery | **Google Cloud project must have "Places API (New)" enabled** — the legacy Places API will NOT work (see §8). |
| `OPENROUTER_API_KEY` | Qualification | Required — no fallback. |
| `OPENROUTER_MODEL` | Qualification | Default `google/gemini-2.5-flash`. Verified against `/models` at runtime. |
| `LOB_TEST_KEY` | Mail proof | **Must start with `test_`.** Live keys are refused in code. |
| `LANDING_BASE_URL` | QR target / landing URL | Where landing pages are hosted; QR points to `{LANDING_BASE_URL}/r/{place_id}.html`. |
| `BRAND_NAME` | Branding | Default `"Your Brand"`. Appears on postcard, landing, mail. |
| `BRAND_TAGLINE` | Branding | Default tagline. |
| `REVIEW_THRESHOLD` | Filter | Default 20. |
| `SEARCH_RADIUS_METERS` | Discovery | Advisory; text query is geo-scoped by the location string. |

> **Security:** API keys used during the build were shared in plaintext chat. **Rotate them** before/after the transfer. Never commit `.env`.

---

## 6. GitHub / PR history

| PR | Scope | State |
|---|---|---|
| #1 | Full pipeline + OpenRouter refactor + live-API fixes | ✅ Merged to `main` |
| #2 | `mailed_test` → `proof_created_test` wording | ✅ Merged to `main` |
| #3 | Remove "CJ Studios"; configurable branding | 🟢 Open (ready to merge) |

`main` currently contains everything except PR #3 (branding), which is open and mergeable.

---

## 7. What was NOT built (and why)

### Intentionally out of scope / not started
- **Storefront photo on the postcard.** Feasible via the Places Photo endpoint (with Google's attribution rules), but not wired up. ~30 min if wanted.
- **Address-to-owner personalization** (e.g. "Owner – {business}"). Not implemented.
- **Real mailing.** By design — Lob test mode only. Going live requires a `live_` key, which the code deliberately refuses until explicitly authorized.
- **Persistent storage / DB, scheduling/automation, dashboard.** CSV + files only.
- **Landing-page hosting.** Pages are generated as static files; they must be deployed to a real host for the QR links to resolve (`LANDING_BASE_URL`).

### Declined (will not build) — see §8
- Rendering a **photorealistic image of the real business owner**.
- Pulling **owner identity/name** from the listing.

---

## 8. Known limitations & gotchas for the new owner

1. **Google "Places API (New)" required.** The legacy Places API returns `REQUEST_DENIED / LegacyApiNotActivated`. Enable **Places API (New)** on the Google Cloud project.
2. **Owner identity is not available from Google Places.** There is no owner name/face field. Any workflow step that needs "the owner by name" cannot be satisfied from the API (only scraping/guessing could, which the brief forbids). Recommended: address mail to "Owner / Manager – {business name}".
3. **Photoreal owner imagery was declined.** Generating a fake image of a real, identifiable person to manipulate them is deceptive, likely unlawful in places, and was explicitly banned by the original brief ("NO fabricated imagery of any real person"). This line holds regardless of spec. Use the business's own storefront photo or a branded template instead.
4. **Lob test objects auto-expire.** Proof URLs are signed and time-limited; the local PDF under `output/postcards/` is the durable copy.
5. **Costs.** Discovery spends Places API requests (Text Search + Details); qualification spends OpenRouter tokens; Lob test mode is free. The 100-request Places guard is the safety net.
6. **Generated outputs are gitignored** — results live on the machine that runs the pipeline, not in the repo.

---

## 9. Suggested next steps for the new team

1. Merge **PR #3** (branding) into `main`.
2. Set `BRAND_NAME`/`BRAND_TAGLINE` and `LANDING_BASE_URL` to real values; deploy the landing pages to that host.
3. (Optional) Add **storefront photo** (Places Photo API, with attribution) and **address-to-owner** formatting — the honest version of "storefront + owner."
4. Rotate all API keys.
5. Decide if/when to go to **live mailing** (requires a Lob `live_` key and an explicit change to the guard — do this deliberately).

---

*Generated as a project handover. The pipeline is a compliant demo: it produces postcard proofs, a ranked CSV, and landing pages — it does not send real mail or generate imagery of real people.*
