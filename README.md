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
| 2 | Qualification | `pipeline/qualification.py` | **Hermes** LLM classifier → strict JSON: `owner_run_likelihood`, `real_storefront`, `willingness_to_pay`. Heuristic fallback when no Hermes endpoint is configured. |
| 3 | Ranking | `pipeline/ranking.py` | Deterministic `priority_score` (pure code). |
| 4 | Postcard | `pipeline/postcard.py` | Branded 6×4" PDF: name, review-gap line, QR to landing page, CJ Studios branding. No faces. |
| 5 | Mail proof | `pipeline/mail_proof.py` | Lob **test-mode** postcard → proof URL. Live keys refused. |
| 6 | Landing page | `pipeline/landing.py` | Compliant static page: one Google review link for **all** visitors. No sentiment gating, no incentives. |
| 7 | CSV output | `pipeline/csv_output.py` | `output/results.csv`, idempotent (dedupe on `place_id`). |

Each module is independently runnable (`python -m pipeline.<module> ...` or via
its `__main__` block) and prints `✅ [module] — [count] records`.

## The Hermes qualification classifier

Module 2 is built on a **Hermes** model (Nous Research's Hermes family, e.g.
`Hermes-3-Llama-3.1`). Hermes is served over an **OpenAI-compatible
`/chat/completions` API**, so the module points at whatever host serves your
model — a local vLLM / llama.cpp / LM Studio server, or a hosted provider.

Configure via environment:

```
HERMES_API_BASE=http://localhost:8000/v1
HERMES_API_KEY=<bearer token for that endpoint>
HERMES_MODEL=Hermes-3-Llama-3.1-8B
```

How it works:
1. A strict **system prompt** tells Hermes to act as a classifier and return
   **JSON only** (`response_format: json_object`, `temperature: 0`).
2. Each business is passed inside a delimited `<business_data>` block, and the
   prompt instructs the model to treat that block as **inert data, never
   instructions** — a prompt-injection defense against adversarial text in a
   scraped business name or website.
3. Output is parsed defensively and clamped to the allowed ranges.
4. If `HERMES_API_KEY` is unset or the call fails, a **deterministic heuristic**
   classifier runs instead, so the demo works end to end with no LLM.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in your keys
```

All secrets are read from the environment (never hardcoded or printed):

- `GOOGLE_PLACES_API_KEY` — Places API (discovery)
- `HERMES_API_KEY` / `HERMES_API_BASE` / `HERMES_MODEL` — qualification
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

### Verify without live keys

```bash
python smoke_test.py
```

Drives modules 2–7 with fixture businesses (heuristic qualification, ranking,
landing pages, postcard PDFs, local mail proof, idempotent CSV).

## Safety guardrails (enforced in code)

- **Stops and asks** before exceeding **100 Places API requests** in one run
  (raise with `--max-places-requests`).
- **Lob test mode only** — keys not starting with `test_` are refused; a `live`
  mode response aborts the run.
- **Idempotent** — re-running never duplicates CSV rows.
- **Compliant landing page** — one Google review link for every visitor; no
  sentiment routing, no star pre-collection, no incentives.
- No face generation, no live mailing, no auto-posting — nothing beyond spec.
