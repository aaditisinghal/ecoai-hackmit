# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Email the maintainer directly, or use
[GitHub's private vulnerability reporting](https://github.com/kbhatnagar1506/EcoAI/security/advisories/new)
for this repository.

Include what you found, how to reproduce it, and its impact if you can.
You'll get an acknowledgment, and a fix or mitigation timeline once it's
assessed.

## Supported versions

Only the code on `main` is maintained. There are no released versions with
independent security support.

## What's already been through a security review

This repository was rebuilt from an earlier, unaudited version. A review of
that original codebase found — and this rebuild fixed — the following, each
with a permanent regression test in
[`tests/test_security_regressions.py`](tests/test_security_regressions.py):

- Unsalted, unsalted-hash password storage (now scrypt via Werkzeug, with
  transparent upgrade from the old hashes)
- A live SMTP credential and a full user database committed to source
  control (removed from the working tree; purged from git history)
- Hardcoded admin credentials in source (now an `is_admin` column, granted
  through the CLI)
- A dashboard endpoint that returned every user's data with no
  authentication check
- An unauthenticated email endpoint that would send to any address on
  request
- Plaintext API keys, stored and displayed in full (now SHA-256 digests,
  shown once at issuance)
- Fake OAuth routes that logged a visitor in as a newly created random
  account with no verification

Full details in [REPORT.md](REPORT.md) and the commit history.
