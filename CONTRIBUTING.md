# Contributing

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(64))" >> .env

export FLASK_APP=wsgi.py
flask db upgrade
```

Run it: `python wsgi.py`, then open <http://localhost:8000>.

## Before opening a PR

```bash
ruff check .              # lint - CI blocks on this
ruff check --fix .        # autofix what it can
pytest                    # full suite
pytest --cov=ecoai --cov-report=term-missing   # see what a new change didn't cover
```

CI (`.github/workflows/ci.yml`) runs lint, the test suite on Python 3.11 and
3.13, a real migration against PostgreSQL, and a scan for committed
credentials. All four have to pass.

## Ground rules for this codebase specifically

- **No comments explaining what code does.** Names should do that. A comment
  is for a non-obvious *why* — a constraint, a bug workaround, something that
  would surprise a reader. If you're tempted to write "increments the
  counter," rename the variable instead and delete the comment.
- **Security-sensitive changes need a regression test.** If you're touching
  auth, API keys, admin access, or anything in `ecoai/security.py`, add a
  test to `tests/test_security_regressions.py`. That file is one test per
  historical vulnerability in this codebase on purpose — the point is that a
  regression fails CI by name, not just "some test somewhere."
- **The carbon model is a formula, not a measurement — say so.** If you
  change coefficients in `ecoai/services/carbon.py` or the surrounding docs,
  don't imply more precision than a FLOPs-based estimate actually has. See
  [REPORT.md](REPORT.md) for why that distinction matters here specifically.
- **New database columns go through Alembic**, not manual schema edits:
  `flask db migrate -m "what changed"` then check the generated migration
  before committing it — autogenerate doesn't always get server defaults or
  index names right.
- **Don't add a dependency for something the standard library or an existing
  dependency already does.** `requirements.txt` is deliberately short.

## Reporting a security issue

Don't open a public issue for it. See the [Security](README.md#security)
section of the README.
