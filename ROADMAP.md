# Roadmap

Phases for Form2Email. Work is organized into initiatives — see
`INITIATIVES.md` for goals, scope, and success criteria per INIT id.

## Now

- **INIT-001 — Relay MVP** *(active)* — verified, expiring form-to-email
  endpoints. See INITIATIVES.md for the full scope; the code in this repo is
  the implementation.

## Next

1. **INIT-002 — Payments & permanence** — Stripe Checkout + webhook flips
   `is_permanent`; renewal-cap decision for free extensions. The schema
   already carries `is_permanent` / `permanent_at`, so this phase needs one
   additive migration at most.
2. **INIT-003 — Abuse protection** — CAPTCHA/honeypot, disposable-email
   blocklist, Redis-backed rate limits, per-email caps. Ship alongside or
   immediately after payments — charging money raises the abuse stakes.

## Later

- **INIT-004 — Accounts & dashboard** — owner login, multi-endpoint
  management, submission history, claim-by-manage-token migration.
- **INIT-005 — Observability & ops** — structured logs, metrics, alerting,
  forward-retry queue, expired-data janitor, operational deployment and
  rollback runbook.

## Notes

- Database: Cloudflare D1 through a mandatory native Worker binding;
  SQLite through SQLAlchemy/Alembic only in tests.
- Email: Cloudflare Email Sending behind the `Mailer` protocol
  (`src/app/mailer/base.py`), using the Worker's `EMAIL` binding.
