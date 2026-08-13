# EcoAI Portal

[![CI](https://github.com/kbhatnagar1506/EcoAI/actions/workflows/ci.yml/badge.svg)](https://github.com/kbhatnagar1506/EcoAI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](.python-version)
[![HackMIT 2025](https://img.shields.io/badge/HackMIT%202025-1st%20Place%2C%20Infosys%20Diamond%20Sponsor-gold.svg)](#hackmit-2025)

Rewrites LLM prompts to cost fewer tokens without changing what they ask for,
then records the energy and emissions avoided.

A Flask application: web UI, JSON API, and a single-file Python SDK.

See [REPORT.md](REPORT.md) for the technical writeup: the problem this is
built for, and a real-GPU experiment that found a real limit in the carbon
model's core assumption.

---

## HackMIT 2025

EcoAI started as a submission to [HackMIT](https://hackmit.org) 2025 and won
**1st place in Infosys's Diamond Sponsor track**, ranked ahead of XiaoPrompt
and EcoPrompt.

The pitch was straightforward: LLM inference has a real, growing energy
footprint (see [REPORT.md](REPORT.md) for the cited numbers), and almost
nobody building on top of a hosted API has any visibility into it. The
hackathon build got a working version of that idea in front of judges in a
weekend — a Flask portal, a prompt-rewriting pass, a first attempt at a
carbon estimate.

Like most hackathon code, it optimized for a working demo over holding up to
scrutiny afterward: secrets committed to source, no real access control, a
"quality score" hardcoded to a constant. None of that reflects on the idea
placing well — it's what a weekend produces under a judging deadline. What's
in this repository now is the post-hackathon rebuild: the same core idea,
re-implemented with real authentication, a real test suite, and a carbon
model checked against actual GPU hardware instead of taken on faith.
[REPORT.md](REPORT.md) has the full technical writeup, including exactly
what changed and why.

---

## What it actually does

Worth being precise, because the previous README described a product that
wasn't in this repository.

**It does:**

- Rewrite prompts across three strategies, protecting code blocks, URLs and
  template placeholders from modification.
- Measure how much content survived each rewrite and report it as a
  `retention_score`.
- Count tokens directly and price them from a published list-price table.
  Tokens saved and dollars avoided are arithmetic, not a model — there is
  nothing to validate beyond "the count is right."
- Estimate energy and CO₂e from token counts using documented, configurable
  coefficients, including per-region grid carbon intensity. This part *is* a
  model, and its accuracy is scoped precisely below.
- **Prompt Studio** — paste a prompt, get the optimized version back from the
  real backend (not a browser mock), with the retention score and exactly
  which transformations fired.
- **Dashboard** — per-account charts of tokens/energy/cost saved over time,
  a model and region breakdown, CSV export, and an emailed impact report.
  Every figure is scoped to the signed-in account; nothing is aggregated
  across users.
- **Admin panel** gated by a real `is_admin` column and a normal login
  session — no separate hardcoded credential.
- Store every optimization as a receipt and expose all of it over a
  versioned JSON API and a Python SDK.

**It does not:**

- Call any LLM. Optimization is deterministic text transformation, not a model.
- Use embeddings. `retention_score` is a lexical measure and is documented as
  one.
- Measure real energy. The carbon figure is computed from a formula, not read
  off a GPU. A real-hardware check (below) confirms what the formula is good
  for and flags what it isn't.
- Fetch live carbon intensity. The region table is a static annual snapshot;
  wiring in ElectricityMaps or WattTime is a small change and an obvious next
  step.
- Prune RAG context or optimize multi-agent workflow graphs.

---

## Quick start

```bash
git clone https://github.com/kbhatnagar1506/EcoAI.git
cd EcoAI

python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env

export FLASK_APP=wsgi.py
flask db upgrade
flask create-admin --username you --email you@example.com

python wsgi.py
```

Then open <http://localhost:8000>.

`flask create-admin` prints an API key once. Copy it — only a hash is stored.

---

## Layout

```
ecoai/                    application package
├── __init__.py           app factory
├── config.py             environment-driven configuration, validated at boot
├── extensions.py         unbound extension singletons
├── security.py           auth decorators
├── forms.py              WTForms definitions (CSRF + validation)
├── errors.py             JSON for /api/*, HTML elsewhere
├── cli.py                flask init-db / create-admin / issue-api-key / import-legacy
├── models/               SQLAlchemy 2.0 models
├── services/             business logic, no Flask imports
│   ├── optimizer.py      prompt rewriting + retention scoring
│   ├── carbon.py         tokens → FLOPs → joules → kWh → gCO₂e
│   ├── tokenizer.py      offline token estimation
│   ├── metrics.py        per-user aggregations
│   ├── pricing.py        model price table
│   ├── receipts.py       ingestion and validation
│   ├── credentials.py    password hashing, API key issuance
│   └── mailer.py         SMTP
├── blueprints/           one per concern
├── templates/            per-blueprint folders
└── static/               css / js / img, all self-hosted

sdk/ecoai_sdk.py          the downloadable SDK, a real file
migrations/               Alembic
tests/                    pytest
```

Configuration comes only from the environment. There are no credentials in the
source tree, and CI fails the build if any appear.

---

## Configuration

Every variable is documented in [.env.example](.env.example). The ones that
matter:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs session cookies. **Required in production** — startup aborts without it. |
| `DATABASE_URL` | SQLite locally, PostgreSQL in production. `postgres://` is rewritten automatically. |
| `ECOAI_ENV` | `development` / `testing` / `production`. Drives cookie security and validation strictness. |
| `APP_BASE_URL` | Public origin. Must be `https://` in production. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Enables Google sign-in. Leave blank to disable it entirely. |
| `MAIL_ENABLED` + `SMTP_*` | Outbound email. Disabled by default; reports render to the logs instead. |
| `CARBON_*` | Emissions coefficients. Defaults documented in `services/carbon.py`. |

`Config.validate()` runs at startup and refuses to boot on anything unsafe —
a missing `SECRET_KEY` in production, SQLite in production, a plain-HTTP base
URL, `MAIL_ENABLED` without credentials.

---

## API

Authenticate with `X-API-Key: <key>` (or `Authorization: Bearer <key>`).

```bash
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "X-API-Key: $ECOAI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Could you please kindly summarize this?", "strategy": "balanced"}'
```

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/optimize` | Optimize a prompt, record a receipt |
| POST | `/api/v1/receipts/batch` | Ingest receipts from elsewhere (idempotent) |
| GET | `/api/v1/receipts` | List your receipts |
| GET | `/api/v1/metrics/summary` | All-time totals |
| GET | `/api/v1/metrics/timeseries` | Daily savings |
| GET | `/api/v1/metrics/models` | Per-model breakdown |
| GET | `/api/v1/me` | Your account |
| GET | `/api/v1/carbon/regions` | Grid intensity table (public) |
| GET | `/healthz` | Liveness probe (public) |

Errors are `{"error": "code", "message": "..."}`. A batch with some events
rejected answers **207** and says which and why — nothing fails silently.

---

## SDK

```python
from ecoai_sdk import EcoAI

eco = EcoAI(api_key="ecoai_...")     # or set ECOAI_API_KEY
result = eco.optimize("Could you please summarize this?", strategy="balanced")

print(result.optimized)
print(f"{result.tokens_saved} tokens saved ({result.reduction_ratio:.1%})")
print(f"{result.co2_g_saved:.6f} g CO2e avoided")
```

Optimization happens server-side, so the SDK and the portal always agree and
improvements reach every client without a package upgrade.

---

## How the carbon estimate works, and how far you can trust it

### The formula

```
tokens → FLOPs → joules → kWh → grams CO₂e
```

1. **FLOPs per token** — `2 × active_parameters`, the standard transformer
   forward-pass estimate from Kaplan et al., *"Scaling Laws for Neural
   Language Models"* (2020), Appendix B [[arXiv:2001.08361](https://arxiv.org/abs/2001.08361)].
   Mixture-of-experts models use active, not total, parameters.
2. **Joules per FLOP** — from accelerator throughput per watt. Default assumes
   an H100 SXM at ~700 W sustaining ~400 TFLOP/s bf16.
3. **PUE** — datacenter overhead, default 1.12.
4. **Grid intensity** — gCO₂e/kWh for the region, from a static table.

Every coefficient is an environment variable (`ecoai/config.py`, `CarbonConfig`).
The model lives in `ecoai/services/carbon.py`, fewer than 300 lines, worth
reading directly rather than trusting this summary.

This is **not** what tools like [CodeCarbon](https://github.com/mlco2/codecarbon)
or [Zeus](https://github.com/ml-energy/zeus) do. Both of those *measure* —
CodeCarbon reads Intel RAPL / `nvidia-smi` counters on the machine actually
running inference; Zeus (Chung, Liu, Xie & Chowdhury, *"Zeus: Understanding
and Optimizing GPU Energy Consumption of DNN Training,"* NSDI 2023, University
of Michigan / ml-energy lab [[paper](https://www.usenix.org/conference/nsdi23/presentation/chung)])
reads GPU power draw through NVML in real time and runs an online search to
find the energy-optimal power cap for a job. Neither is integrated here.
Neither *can* be, for the primary use case: when EcoAI optimizes a prompt
you're about to send to a hosted API, nobody but that provider has NVML
access to the chip that will run it. Zeus and CodeCarbon apply to inference
you host yourself; this formula is what's left when you don't.

### What was actually checked on real hardware

Rather than take that gap on faith, we provisioned a real GPU (an NVIDIA L4 on
Google Compute Engine) and ran a small open-weight model — Qwen2.5-1.5B-Instruct
— through [vLLM](https://github.com/vllm-project/vllm), with generation
wrapped in Zeus's `ZeusMonitor` reading actual NVML power samples. Two
requests: the same prompt, once as originally written and once run through
EcoAI's own optimizer.

The result was a real finding, not a confirmation of the formula: **measured
energy barely moved between the two**, because output generation was capped
at a fixed `max_tokens` and dominated the request's total energy far more than
the shortened input did. Autoregressive decoding pays a real GPU-energy cost
per *output* token; a shorter prompt only shrinks the one-time prefill pass,
which is a small slice of total energy on a typical request. Cutting input
tokens is still real — it's counted exactly, not modeled — but it doesn't
translate into a proportional cut in a request's actual energy the way the
formula's linear `tokens → joules` relationship might imply.

What the formula *is* good for, and what this check didn't contradict: holding
token count fixed and comparing across models or regions. A bigger model
costing more energy per token, or the same request costing less in a
cleaner-grid region, is true by construction of the arithmetic — there's no
empirical claim being smuggled in there. What it isn't validated for is the
thing the dashboard's headline number implies: that shortening *this* prompt
measurably cut *this* request's real energy. For output-heavy requests, it
mostly didn't, in the one real test we ran.

We don't have the exact joule/watt figures from that run to publish here —
they lived on the GPU instance and weren't saved before it was torn down.
The finding above is the honest, reproducible part: rerun `sdk/` or hit
`/api/v1/optimize` against a self-hosted vLLM + Zeus setup and you'll see the
same shape of result, because it follows from how autoregressive decoding
actually spends energy, not from anything specific to that one run.

---

## Development

```bash
pip install -r requirements-dev.txt

pytest                  # 280 tests
pytest --cov=ecoai      # coverage
ruff check .            # lint
ruff check --fix .      # autofix
```

CI runs lint, tests on Python 3.11 and 3.13, migrations against a real
PostgreSQL, and a credential scan.

### Migrations

```bash
export FLASK_APP=wsgi.py
flask db migrate -m "what changed"   # generate
flask db upgrade                     # apply
flask db check                       # fail if models drifted from migrations
```

---

## Deploying to Heroku

```bash
heroku create your-app-name
heroku addons:create heroku-postgresql:essential-0

heroku config:set \
  ECOAI_ENV=production \
  SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')" \
  APP_BASE_URL=https://your-app-name.herokuapp.com

git push heroku main
heroku run flask create-admin --username you --email you@example.com
```

`DATABASE_URL` is set by the Postgres add-on. The `release` phase in the
Procfile runs `flask db upgrade` on every deploy.

**Postgres is required in production.** SQLite on an ephemeral filesystem
discards every account and receipt on each dyno restart, so the app refuses to
start with a SQLite URL when `ECOAI_ENV=production`.

---

## Migrating from the pre-2.0 database

```bash
export FLASK_APP=wsgi.py
flask db upgrade
flask import-legacy legacy/ecoai_portal.db --dry-run   # preview
flask import-legacy legacy/ecoai_portal.db
```

- **API keys keep working.** The old schema stored them in cleartext, so they
  are hashed into the new column during import. Afterwards they are no longer
  recoverable from the database.
- **Passwords keep working.** The old unsalted SHA-256 digests are carried
  across and transparently upgraded to scrypt the first time each user signs
  in successfully.
- The importer reads by column name, so it handles both historical column
  orderings.

---

## Security

- Passwords: scrypt via Werkzeug, with transparent upgrade from the legacy
  unsalted SHA-256.
- API keys: 256 bits of CSPRNG output, stored as SHA-256, displayed once.
- CSRF on every form; the token API validates its own on cookie-authenticated
  requests.
- Rate limits on sign-in, sign-up, API and report email.
- Admin access via the `is_admin` column, granted by CLI.
- CSP restricted to `'self'` — no CDN, no third-party JavaScript.
- Secure cookies, HSTS, `X-Frame-Options: DENY`, `nosniff`.

`tests/test_security_regressions.py` has one test per historical
vulnerability. If one fails, a specific past defect has returned.

Found something? See [SECURITY.md](SECURITY.md) — don't open a public issue.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, conventions, and what CI
checks. This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
