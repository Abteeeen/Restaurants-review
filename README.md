# Local-Business Review-Outreach Pipeline (DEMO)

A demo pipeline that finds low-review local businesses, qualifies the best
prospects, generates a personalized postcard **proof** for each, and logs
everything to a CSV as proof of work.

> **This is a DEMO.** No real mail is ever sent — Lob is used in **test mode**
> to produce postcard PDF proofs only. No faces or fabricated imagery of real
> people are generated. Live mail endpoints are refused in code.

## Pipeline

| # | Module | File | What it does |
|---|--------|------|--------------|
| 1 | Discovery | `pipeline/discovery.py` | Google Places **Text Search → Place Details** (API only, no scraping). Filters `user_ratings_total < REVIEW_THRESHOLD` **and** `business_status == OPERATIONAL`. |
| 2 | Qualification | `pipeline/qualification.py` | **OpenRouter** (`google/gemini-2.5-flash`) LLM classifier → strict JSON: `owner_run_likelihood`, `real_storefront`, `willingness_to_pay`. **No fallback** — fails loudly per row. |
| 3 | Ranking | `pipeline/ranking.py` | Deterministic `priority_score` (pure code). |
| 4 | Postcard | `pipeline/postcard.py` | Branded 6×4" PDF: name, review-gap line, QR to landing page, configurable branding (`BRAND_NAME`). No faces. |
| 5 | Mail proof | `pipeline/mail_proof.py` | Lob **test-mode** postcard → proof URL. Live keys refused. |
| 6 | Landing page | `pipeline/landing.py` | Compliant static page: one Google review link for **all** visitors. No sentiment gating, no incentives. |
| 7 | CSV output | `pipeline/csv_output.py` | `output/results.csv`, idempotent (dedupe on `place_id`). |

Each module is independently runnable (`python -m pipeline.<module> ...` or via
its `__main__` block) and prints `✅ [module] — [count] records`.

## The OpenRouter qualification classifier

Module 2 calls **OpenRouter** (OpenAI-compatible) at
`POST https://openrouter.ai/api/v1/chat/completions` with model
**`google/gemini-2.5-flash`**. Configure via environment:

```
OPENROUTER_API_KEY=<your OpenRouter key>
OPENROUTER_MODEL=google/gemini-2.5-flash
```

How it works:
1. **Model verification first.** On each run the module fetches OpenRouter's
   live `/models` list and confirms the configured model id is present. If it
   is not, the run **stops and reports** — it never silently substitutes a
   different model.
2. A strict **locked system prompt** tells the model to act as a classifier and
   return **JSON only** (`response_format: json_object`, `temperature: 0`).
3. Each business is passed inside a delimited `<business_data>` block, and the
   prompt instructs the model to treat that block as **inert data, never
   instructions** — a prompt-injection defense against adversarial text in a
   scraped business name or website.
4. Output is parsed and validated into the strict schema. Missing/invalid keys
   are treated as a failed call (no invented defaults).

### No silent fallback — fail loudly

This is deliberate. There is **no heuristic fallback**:

- **Missing `OPENROUTER_API_KEY`** or **unavailable model** → the run is
  aborted with a clear error.
- A per-business call that **errors or times out** is retried (**20s timeout**,
  **max 2 retries** with exponential backoff). If it still fails, that row is
  marked `status="QUALIFICATION_FAILED"`, its classifier fields are left empty
  (**never fabricated**), and it is **not** pitched (no postcard / mail proof) —
  but it still appears in the CSV.
- Every row records a **`qualification_source`** column
  (`openrouter:gemini-2.5-flash` on success, `FAILED` otherwise), so the demo
  can never present fabricated AI output as a real classification.

Per-run the module prints:
`✅ qualification — N classified via OpenRouter, M failed`.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
```

All secrets are read from the environment (never hardcoded or printed):

- `GOOGLE_PLACES_API_KEY` — Places API (discovery)
- `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` — qualification (required; no fallback)
- `LOB_TEST_KEY` — **must** start with `test_`; live keys are refused
- `LANDING_BASE_URL` — where landing pages are hosted (QR target)

## Run

```bash
python run.py --category "dentist" --location "Brisbane QLD"
```

Produces:
- `output/results.csv` — ranked rows (one per prospect, deduped on `place_id`)
- `output/postcards/<place_id>.pdf` — one postcard proof per prospect
- `landing/pages/r/<place_id>.html` — one compliant landing page per prospect
- a Lob **test-mode** proof URL per row (or a `LOCAL-PROOF:` reference if no
  Lob key is set)

Useful flags: `--radius`, `--review-threshold`, `--max-places-requests`,
`--limit` (only process the top-N ranked prospects).

### Verify without live network

```bash
python smoke_test.py
```

Drives modules 2–7 with fixture businesses. Because qualification has no
fallback, the test injects deterministic doubles for the OpenRouter calls and
verifies both paths: the happy path (ranking, landing pages, postcard PDFs,
mail proof, idempotent CSV) and a failed classification (marked
`QUALIFICATION_FAILED`, not fabricated, not pitched, still written to the CSV).

## Safety guardrails (enforced in code)

- **Stops and asks** before exceeding **100 Places API requests** in one run
  (raise with `--max-places-requests`).
- **Lob test mode only** — keys not starting with `test_` are refused; a `live`
  mode response aborts the run.
- **Idempotent** — re-running never duplicates CSV rows.
- **Compliant landing page** — one Google review link for every visitor; no
  sentiment routing, no star pre-collection, no incentives.
- No face generation, no live mailing, no auto-posting — nothing beyond spec.
