# Form2Email

Any HTML form, delivered to your inbox — a form-to-email relay with expiring
endpoints, like a temporary URL service for forms. Register a destination
email **and the domain your form lives on**, verify the email, and get a
public URL you can point any HTML form at. Every signup lands in your inbox
as an email (with all fields), and entries are stored per endpoint.
Management stays with you, in your inbox.

Typical uses: waitlist signups, contact forms, quote requests, RSVPs,
feedback boxes — any static site that can't receive a form POST itself. The
hosted service is at **https://form2email.terragohan.com**, with copy-paste
guides for those forms at
[form2email.terragohan.com/guides](https://form2email.terragohan.com/guides).

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

Python 3.13 · FastAPI on Cloudflare Python Workers · Cloudflare D1 and Email
Sending bindings · Jinja2 templates · pytest. SQLite + SQLAlchemy/Alembic are
test-only utilities, not runtime fallbacks.

## Quickstart

Requires `uv` 0.13.4 or newer for Pywrangler. Both database access and outbound
mail require Cloudflare bindings; there is no alternate runtime provider.

```bash
uv run pywrangler d1 migrations apply form_to_email --local
uv run pywrangler dev
```

The sender domain must be onboarded to Cloudflare Email Sending before real
mail can be delivered.

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

Deployment is Wrangler-only and lives in this repository: `src/worker.py` is
the ASGI entrypoint, `wrangler.toml` configures the route and bindings, and
`migrations/` contains the D1 schema. The existing `form_to_email` database is
reused without a data migration.

Before the first deploy, onboard `terragohan.com` in the Cloudflare dashboard
under **Compute → Email Service → Email Sending**. Then:

```bash
uv run pywrangler d1 migrations apply form_to_email --remote
uv run pywrangler secret put ADMIN_TOKEN
uv run pywrangler deploy
```

`BASE_URL` and `MAIL_FROM` are non-secret vars in `wrangler.toml`. D1 and Email
Sending use bindings, so the Worker needs no Cloudflare API token or mail
provider key at runtime. Logs are available with `uv run pywrangler tail`.

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
uv run pytest        # endpoints, forms, D1/email bindings, expiry, rate limits, CORS, SEO
uv run pywrangler deploy --dry-run   # verify the Worker bundle
uv run alembic revision --autogenerate -m "..."   # after model changes
```

Tokens in URLs are random 256-bit values; only SHA-256 hashes are stored, so a
database leak doesn't expose live form or management URLs.

## Roadmap

Future work is organized as initiatives (`INITIATIVES.md`) sequenced in
`ROADMAP.md`: payments & permanence (INIT-002) and abuse protection
(INIT-003) are next; accounts/dashboard (INIT-004) and observability
(INIT-005) later.
