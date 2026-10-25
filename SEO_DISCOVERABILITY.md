# SEO & Discoverability

Internal reference for how Form2Email's public website is optimized for
search engines and AI-powered search (ChatGPT search, Perplexity, etc.).
Last updated: 2026-10-10.

## Target search queries

Primary (homepage):

- free HTML form to email · send HTML form submissions to email · receive
  website form submissions by email · contact form without backend · static
  website contact form · HTML form email service · form-to-email API · form
  to email without signup · Formspree / FormSubmit / Web3Forms alternative

Per-guide intents (each guide is one real-world form people build):

| Route | Query intent |
|---|---|
| `/guides/contact-form` | contact form without backend / without PHP |
| `/guides/waitlist-form` | waitlist signup form for a launch page |
| `/guides/newsletter-signup` | newsletter signup form in HTML |
| `/guides/feedback-form` | customer feedback / rating form |
| `/guides/quote-request-form` | quote request form for a service business |
| `/guides/booking-form` | appointment booking form for a website |
| `/guides/rsvp-form` | RSVP / event registration form |
| `/guides/job-application-form` | job application form for a careers page |
| `/guides/support-request-form` | support request form without ticketing |
| `/guides/order-form` | simple order form without a shop backend |

## Implemented SEO features

- Unique `<title>` + meta description on every public page; exactly one H1
  per page (enforced by tests).
- Absolute canonical URLs built from `BASE_URL` (`settings.base_url`).
- Open Graph + Twitter card metadata (`summary_large_image`) on all public
  pages; social card at `src/app/static/og-image.png` (1200×630, brand style;
  source: `src/app/static/og-image.svg`).
- JSON-LD: `WebApplication` on the homepage (accurate `offers` price 0, no
  ratings/reviews/Organization — operator info is not publicly established);
  `BreadcrumbList` on every guide.
- `/robots.txt` and `/sitemap.xml` served by the app (see below).
- `noindex, nofollow` on token/user pages: `/f/{token}`, `/manage/{token}`,
  `/verify/{token}`, and the 404 page.
- Branded HTML 404 page for unknown paths; API/form paths (`/api/*`,
  `/f/*`, `/manage/*`, `/verify/*`, `/healthz`) keep their JSON 404s —
  endpoint behavior is unchanged.
- Server-rendered HTML throughout (Jinja2) — no client-side rendering
  barrier for crawlers. The homepage setup tool's *result* UI is JS-only,
  but all explanatory content is in static HTML.
- Visible FAQ on the homepage (`/#faq`), eight questions answered from
  actual product behavior. Deliberately no FAQ structured data.
- Internal navigation: header (Create / How it works / Guides / FAQ) and
  footer (incl. For coding tools, API info) on every page; guides
  cross-link siblings; `/guides` hub lists all ten.
- Discovery routes for AI coding tools already existed and are unchanged:
  `/llms.txt`, `/api/info`, `/for-coding-tools` (all rate-limited 3/min per
  IP, shared bucket).

## Indexable routes

Included in `sitemap.xml` (14 URLs, source of truth: `SITEMAP_PATHS` in
`src/app/main.py`):

`/`, `/how-it-works`, `/for-coding-tools`, `/guides`, and the ten
`/guides/<slug>` pages.

Not indexable by design: `/f/{token}`, `/manage/{token}`, `/verify/{token}`
(noindex + robots disallow), `/api/*`, `/healthz`, `/llms.txt` (allowed but
excluded from the sitemap — it's for agents, not search), `/docs` +
`/openapi.json` (allowed, excluded from sitemap).

## Metadata conventions

- `base.html` blocks: `title`, `meta_description`, `robots_meta` (empty =
  indexable), `jsonld`. OG/Twitter titles reuse the `title` and
  `meta_description` blocks.
- Canonical/OG/Twitter tags render only when the route passes
  `canonical_path` to `render()`; absolute URLs are
  `settings.base_url.rstrip('/') + canonical_path`. Token pages pass no
  `canonical_path`, so they emit no canonical/social tags (they're noindex).
- Guide pages are registered in `GUIDES` in `src/app/main.py` (slug → template,
  title, description, summary) and extend `guide-base.html`; sitemap and hub
  page derive from the same dict. **Add a new guide by adding one GUIDES
  entry + one template — sitemap, hub, and tests pick it up automatically**
  (update the count assertion in `tests/test_seo.py::test_sitemap_xml`).

## Sitemap behavior

`GET /sitemap.xml` → `application/xml`, `<url><loc>` entries only (no
lastmod — nothing meaningful to derive it from), built from `BASE_URL`.
Intentionally **not** rate-limited: crawler fetches must never 429. Same
for `/robots.txt`. (The `/api/info` family stays rate-limited.)

## Crawler policy

`robots.txt` (`src/app/main.py::robots_txt`):

- `User-agent: *` — `Allow: /` with disallows for `/api/`, `/manage/`,
  `/verify/`, `/f/`, `/healthz`.
- Explicit `User-agent: OAI-SearchBot` group (ChatGPT search indexing) with
  the same restrictions — OAI-SearchBot is deliberately permitted.
- GPTBot (training crawler) policy is **unchanged**: no specific rule, it
  falls under the wildcard group. Don't add one without a project decision.
- `Sitemap: <BASE_URL>/sitemap.xml`.

Verified live on 2026-10-10: OAI-SearchBot, Googlebot, bingbot, and GPTBot
user-agents all received HTTP 200 on public pages — no WAF-level bot
blocking is active.

**Platform note (resolved 2026-10-10):** before this deploy, `/robots.txt`
showed Cloudflare's free-plan *Content Signals Policy* fallback — served only
because the origin returned 404. Per Cloudflare's docs, the fallback
disappears once the origin serves its own `robots.txt`, and no Bot
Preference Sync is enabled on the zone — confirmed live: the app-served file
(with the Sitemap line and OAI-SearchBot group) is now served as-is, no
dashboard change needed. If someone later enables Bot Preference Sync,
Cloudflare will *prepend* managed directives to this file.
Side note: HEAD requests currently return 405 (FastAPI default) — harmless
for search crawlers, which GET.

## Verified claims (source: code + README/ROADMAP)

Safe to publish: currently free (payments are roadmap INIT-002); no
accounts; email verification required before relay; 7-day endpoint TTL with
free unlimited extensions + revival; permanence operator-granted; origin
binding (exact hostname match); rate limits (5 creates/IP/h, 30
submits/IP/min with backoff to 5 min, 3 verification emails/address/day);
64 KB body cap and per-field caps; extra fields included in the relay;
Reply-To = visitor; owner-only mail; only token hashes stored; submissions
stored per endpoint.

Not claimed anywhere (don't add): CAPTCHA/honeypot (INIT-003), guaranteed
delivery, specific hosting integrations, file uploads (dropped), payment
processing, customer autoresponders, company/Organization details.

Needs owner decision/verification:

- Public contact channel for permanence requests ("granted by the operator
  on request" — but no contact address is published).
- Revisit all "free" copy + the homepage JSON-LD `offers` when INIT-002
  (payments) ships.

## Remaining manual actions

Deployment happened 2026-10-10 via `deploy.sh` (AWS profile
`terragohan-email`) — stack `form2email` in us-east-2. Verified live:
homepage metadata/JSON-LD, all 14 sitemap URLs, app-served robots.txt,
og-image, branded 404, OAI-SearchBot + Googlebot access, `/llms.txt` +
`/api/info` unchanged. Nothing left here except search-engine onboarding:

### Launch checklist (owner accounts required)

- [ ] Google Search Console: verify property `form2email.terragohan.com`
  (DNS TXT via Cloudflare is easiest).
- [ ] Submit `https://form2email.terragohan.com/sitemap.xml` in Search
  Console → Sitemaps.
- [ ] Bing Webmaster Tools: add site (import from Search Console), submit
  the same sitemap. IndexNow is optional at this size — Bing's import +
  sitemap is enough.
- [ ] URL Inspection (Search Console) on `/`, `/guides`, and 2–3 guides;
  request indexing for `/` and `/guides`.
- [ ] Rich Results Test on `/` (WebApplication) and one guide
  (BreadcrumbList) to confirm the JSON-LD parses.
- [ ] Re-check OAI-SearchBot access post-deploy:
  `curl -A "OAI-SearchBot/1.0" https://form2email.terragohan.com/guides`
  → expect 200.
- [ ] Share-debug a guide URL (e.g. Slack/social preview) to confirm the OG
  image renders.
- [ ] Confirm no `noindex` leaks onto public pages (tests cover this) and
  that token pages stay unindexed.
