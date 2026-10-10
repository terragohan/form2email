# Form2Email

Waitlist signup collection, delivered to your inbox — a form-to-email relay
with expiring endpoints, like a temporary URL service for forms. Register a
destination email **and the domain your form lives on**, verify the email,
and get a public URL you can point any HTML form at. Every signup lands in
your inbox as an email (with all fields), and entries are stored per
endpoint. Management stays with you, in your inbox.

- **Temporary by default:** endpoints expire 7 days after verification.
  Free extensions add another 7 days each.
- **Permanent is the paid tier:** the schema already supports it
  (`is_permanent`); payments land in INIT-002 (see `ROADMAP.md`).
- **Verification required:** nothing relays until the destination email owner
  clicks the verification link.
- **Owner-only mail:** the service only ever emails the endpoint owner —
  waitlist joiners (form visitors) never receive mail from us.
- **Origin-bound:** submissions are only accepted from exactly the domain you
  registered — subdomains must be registered explicitly.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2 + Alembic (SQLite now, Postgres by
`DATABASE_URL`) · outbound mail via Resend (HTTP) or plain SMTP — any
provider, or a local Postfix/relay (`MAIL_DRIVER`) · Jinja2 templates · pytest

## Quickstart

```bash
uv sync
cp .env.example .env        # add your RESEND_API_KEY
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Without a Resend API key the app boots and the test suite passes, but real
delivery needs a key. Note: Resend's `onboarding@resend.dev` sender only
delivers to your own Resend account email until you verify a domain.

## Walkthrough

Create an endpoint (rate-limited to 5/hour per IP; verification emails to any
single address are capped at 3/day across all IPs). You provide the email that
submissions go to and the domain the form lives on — both are stored, and the
domain is bound to the endpoint:

```bash
curl -s -X POST http://localhost:8000/api/endpoints \
  -H 'content-type: application/json' \
  -d '{"destination_email": "you@example.com", "origin": "yoursite.com"}'
```

```json
{
  "public_url": "http://localhost:8000/f/<public_token>",
  "manage_url": "http://localhost:8000/api/endpoints/<manage_token>",
  "destination_email": "you@example.com",
  "origin": "yoursite.com",
  "verification": "pending"
}
```

`origin` accepts a bare domain (`yoursite.com`), an origin
(`https://yoursite.com`), or a full URL — it's normalized to the hostname.
Check your inbox and click the `http://localhost:8000/verify/<token>` link —
the endpoint is now active for 7 days.

Point any form at the public URL, or open it in a browser for a built-in form:

```html
<form action="http://localhost:8000/f/<public_token>" method="post">
  <input name="name" required>
  <input name="email" type="email" required>
  <textarea name="message" required></textarea>
  <!-- optional: send browser users onward after submit -->
  <input type="hidden" name="_redirect" value="https://yoursite.com/thanks">
  <button type="submit">Send</button>
</form>
```

JSON works too (`content-type: application/json`). Fields `name`, `email`,
`subject`, `message` are mapped into the relay email; anything else is
appended as "additional fields". The sender's `email` becomes the relay's
`Reply-To`, and the email footer records which origin the form lives on.

**Origin enforcement:** browsers send an `Origin` header with form posts. A
post whose `Origin` (or `Referer`) hostname doesn't exactly match the
registered origin is rejected with `403` — so nobody can embed your
endpoint on their own site, and even a subdomain of your domain must be
registered separately. Requests with no origin headers at all (curl,
server-to-server, mobile apps) are still accepted; register the origin your
real users' browsers will send.

Manage the endpoint with the manage URL:

```bash
curl -s http://localhost:8000/api/endpoints/<manage_token>           # status
curl -s -X POST http://localhost:8000/api/endpoints/<manage_token>/extend  # +7 days
curl -s -X POST http://localhost:8000/api/endpoints/<manage_token>/verification  # resend link
```

Error semantics: `403` unverified · `410` expired · `413` body over 64 KB ·
`422` field over its length cap · `429` rate limited · `502` relay delivery
failed (submission is still stored).

Submissions are capped per client IP (30/minute by default). An IP that keeps
posting past the cap is throttled with exponential backoff — each rejected
attempt doubles the lockout from 1s up to 5 minutes, and the `429` response
carries a `Retry-After` header. A successful submission clears the backoff.
Bodies over 64 KB are rejected with `413` before parsing; individual fields
have length caps (message: 20,000 characters, extras: 20 fields × 1,000) and
over-length values get a `422`. File uploads and nested JSON are dropped.

**Integrating from code?** Coding tools can set up an endpoint end to end:
see `/for-coding-tools` for a paste-ready agent prompt, `/llms.txt` for the
llms.txt agent convention, and `/api/info` for the machine-readable API
description. Those discovery routes are static but rate-limited (3/minute
per IP, shared bucket) — cache the response in your project rather than
fetching it at runtime.

## Deployment

All deployment config lives in the sibling repo **`../infra/form2email`**
(SAM template, Cloudflare Worker + `wrangler.toml`, D1 migrations, Terraform
for SSM secrets, `deploy.sh`, and the runbooks `DEPLOY-LAMBDA.md` /
`DEPLOY-DROPLET.md`). This repo keeps only application code — plus
`Dockerfile.lambda`, which must stay here because SAM requires the
Dockerfile inside the container build context.

The service runs behind a path prefix — all generated URLs come from
`BASE_URL`. Two ready-made paths, both fronted by the same Cloudflare Worker
(apex routing, `ORIGIN_TOKEN` gate enforced by `OriginTokenMiddleware` in
`app/main.py`; disabled when unset, as in local dev) — switching between
them is one `ORIGIN_BASE` line in `../infra/form2email/wrangler.toml`:

- **Lambda + Cloudflare D1** (primary) — see `../infra/form2email/DEPLOY-LAMBDA.md`
- **DigitalOcean droplet + SQLite** (fallback) — see `../infra/form2email/DEPLOY-DROPLET.md`

### Granting permanence (operator-only)

Permanence is granted manually by the service operator. With `ADMIN_TOKEN`
configured, an endpoint is made permanent via the admin API:

```bash
curl -X POST -H "X-Admin-Token: …" https://<your-host>/api/admin/endpoints/<endpoint-id>/permanent
```

and revoked with `DELETE` on the same URL (revocation restarts the usual
7-day window). Endpoint ids are looked up in the database — raw tokens are
unrecoverable by design. As a fallback, the same can be done directly in SQL:

```sql
UPDATE endpoints SET is_permanent = 1, permanent_at = <now> WHERE id = '<endpoint-id>';
```

## Development

```bash
uv run pytest        # 33 tests: endpoints, forms, expiry, rate limits, origin checks
uv run alembic revision --autogenerate -m "..."   # after model changes
```

Tokens in URLs are random 256-bit values; only SHA-256 hashes are stored, so a
database leak doesn't expose live form or management URLs.

## Roadmap

Future work is organized as initiatives (`INITIATIVES.md`) sequenced in
`ROADMAP.md`: payments & permanence (INIT-002) and abuse protection
(INIT-003) are next; accounts/dashboard (INIT-004) and observability
(INIT-005) later.
