# Initiatives

Long-lived workstreams for Form2Email. Each initiative has a goal, scope, and
success criteria. `ROADMAP.md` sequences them into phases; every roadmap item
references an INIT id, and every initiative lists its current phase.

Status legend: **done** | **active** | planned

---

## INIT-001 — Relay MVP — **active**

**Goal:** Waitlist signup collection, delivered to the owner's inbox — a
working form-to-email relay with verified, expiring endpoints. The owner
manages their waitlist in their own inbox/tools; the service never emails
form visitors.

**Scope:**
- Endpoint creation takes destination email + the form's origin domain; both
  stored, linked to a unique public URL + manage URL (hashes only in DB)
- Email verification (24h, single-use, rotatable) required before activation
- Public form page + submission relay via Resend; entries stored per endpoint
- Origin enforcement on submit: browser Origin/Referer must exactly match the
  stored domain (no implicit subdomains); headerless clients
  (curl/server-to-server) allowed
- 7-day TTL from verification; free extension; permanent flag in schema
- Basic in-memory per-IP rate limiting on create and submit, with exponential
  backoff (doubling lockouts) for IPs that keep submitting past the cap;
  verification emails to any single address capped per day across all IPs
- Submission size limits: 64 KB body cap (413), per-field length caps (422),
  file uploads and nested JSON dropped
- Alembic migrations from day one; SQLite by default, Postgres by env var

**Out of scope (decided):** no email to form visitors (no double opt-in), no
inbound/reply-to-command processing, no owner-side actions in relay emails —
collection and delivery only. Revisit if users ask.

**Success criteria:** `uv run pytest` green; full create → verify → submit →
relay walkthrough works end to end against the ASGI app.

**Roadmap phase:** Now.

---

## INIT-002 — Payments & permanence — planned

**Goal:** Users can pay to make an endpoint permanent (never expires).

**Scope:**
- Stripe Checkout session created from the manage page/URL
- Stripe webhook flips `is_permanent` / sets `permanent_at` on the endpoint
- Decide and enforce a renewal cap for free extensions
- Pricing copy on the form/verified pages

**Success criteria:** In Stripe test mode, completing checkout makes the
endpoint permanent within seconds; webhook signature verification rejects
forged calls; expired-permanent edge cases covered by tests.

**Roadmap phase:** Next.

---

## INIT-003 — Abuse protection — planned

**Goal:** The service cannot be used to spam, bomb, or scrape.

**Scope:**
- (MVP already ships: match-or-absent origin allowlist; strict mode — reject
  posts with no Origin header — is a config option to add here)
- CAPTCHA or honeypot on the public form page
- Disposable-email domain blocklist on endpoint creation
- Persistent rate limiting (Redis) replacing the in-memory limiter
- Per-destination-email verification cap — shipped in the MVP (3/day per
  address, across all IPs); still open: pending-verification caps
- Submission length caps — shipped in the MVP (body + per-field limits);
  still open: header-injection screening

**Success criteria:** Red-team pass: scripted bursts are throttled without
affecting legitimate traffic; no outbound mail to blocklisted domains.

**Roadmap phase:** Next.

---

## INIT-004 — Accounts & dashboard — planned

**Goal:** Owners can manage many endpoints from one login.

**Scope:**
- Owner accounts (email + magic link or password)
- Dashboard listing endpoints, status, expiry, submission counts
- Per-endpoint submission history viewer
- Migration path for anonymous manage-token endpoints into accounts

**Success criteria:** An owner can claim an existing manage-token endpoint,
see it in the dashboard, and revoke/regenerate tokens.

**Roadmap phase:** Later.

---

## INIT-005 — Observability & ops — planned

**Goal:** The service is debuggable and self-healing in production.

**Scope:**
- Structured logging (JSON) with request IDs
- Metrics: submissions, forward failures, verification funnel
- Alerting on forward-failure rate
- Forward-retry queue for failed relays
- Janitor job purging expired endpoints and old submissions
- Postgres-by-default deployment guide + Dockerfile

**Success criteria:** A failed Resend call is visible in metrics and retried
automatically; expired data is purged on schedule; one-command deploy.

**Roadmap phase:** Later.
