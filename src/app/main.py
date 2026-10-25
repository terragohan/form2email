from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from app.config import Settings, get_settings
from app.db import get_store
from app.render import render
from app.routers import admin, endpoints, forms, meta, verify
from app.services import endpoints as svc
from app.store.base import Store


app = FastAPI(title="Form2Email", version="0.1.0")
app.include_router(endpoints.router)
app.include_router(verify.router)
app.include_router(forms.router)
app.include_router(meta.router)
app.include_router(admin.router, include_in_schema=False)
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).parent / "static"),
    name="static",
)

# Real-world form guides — one page per form people actually build. The
# template renders guide-base.html with `guide` in context; metadata lives
# here so titles/descriptions stay consistent with the sitemap and hub page.
GUIDES = {
    "contact-form": {
        "template": "guide-contact-form.html",
        "name": "Contact form",
        "title": "Contact Form Without a Backend — Form2Email",
        "description": (
            "Add a contact form to any website with plain HTML. Form2Email "
            "emails every submission to your inbox — no PHP, no server code."
        ),
        "summary": "The classic name/email/message form for your contact page or site footer.",
    },
    "waitlist-form": {
        "template": "guide-waitlist-form.html",
        "name": "Waitlist form",
        "title": "Waitlist Signup Form for Your Launch — Form2Email",
        "description": (
            "Collect waitlist signups on your coming-soon page with a simple "
            "HTML form. Every signup lands in your email inbox."
        ),
        "summary": "Email-only signup for a coming-soon or pre-launch page.",
    },
    "newsletter-signup": {
        "template": "guide-newsletter-signup.html",
        "name": "Newsletter signup",
        "title": "Newsletter Signup Form in Plain HTML — Form2Email",
        "description": (
            "Get every newsletter signup delivered to your inbox with a "
            "one-field HTML form — no backend or mailing-list software needed."
        ),
        "summary": "A single email field that notifies you of each new subscriber.",
    },
    "feedback-form": {
        "template": "guide-feedback-form.html",
        "name": "Feedback form",
        "title": "Customer Feedback Form in HTML — Form2Email",
        "description": (
            "Collect ratings and comments with a plain HTML feedback form. "
            "Submissions arrive in your inbox with the sender as reply-to."
        ),
        "summary": "Star rating plus comments, delivered as one email per response.",
    },
    "quote-request-form": {
        "template": "guide-quote-request-form.html",
        "name": "Quote request form",
        "title": "Quote Request Form for Service Businesses — Form2Email",
        "description": (
            "Let clients describe the job, budget, and timeline in one form. "
            "Quote requests arrive by email — no backend to maintain."
        ),
        "summary": "Pre-qualify leads with project scope, budget, and timeline fields.",
    },
    "booking-form": {
        "template": "guide-booking-form.html",
        "name": "Booking form",
        "title": "Appointment Booking Request Form — Form2Email",
        "description": (
            "Collect booking requests with date, time, and service from your "
            "website. Requests land in your inbox — you confirm by replying."
        ),
        "summary": "Date, time, and service fields for appointment requests by email.",
    },
    "rsvp-form": {
        "template": "guide-rsvp-form.html",
        "name": "RSVP form",
        "title": "RSVP & Event Registration Form — Form2Email",
        "description": (
            "Collect RSVPs on your event page with a plain HTML form. Names, "
            "guest counts, and meal choices arrive by email."
        ),
        "summary": "Attendance, guest counts, and preferences for your event page.",
    },
    "job-application-form": {
        "template": "guide-job-application-form.html",
        "name": "Job application form",
        "title": "Job Application Form for Your Careers Page — Form2Email",
        "description": (
            "Receive job applications by email with a plain HTML form. "
            "Applicants link their résumé; you reply straight from your inbox."
        ),
        "summary": "Screening questions and résumé links for a small careers page.",
    },
    "support-request-form": {
        "template": "guide-support-request-form.html",
        "name": "Support request form",
        "title": "Support Request Form in HTML — Form2Email",
        "description": (
            "Give customers a support form that emails you their issue and "
            "order number. No ticketing system or backend required."
        ),
        "summary": "Issue, order number, and contact fields routed to your inbox.",
    },
    "order-form": {
        "template": "guide-order-form.html",
        "name": "Order form",
        "title": "Simple Order Form Without a Shop Backend — Form2Email",
        "description": (
            "Take orders with a plain HTML form — details arrive by email and "
            "you invoice separately. No cart or checkout software needed."
        ),
        "summary": "Product, quantity, and delivery details for cart-free orders.",
    },
}

SITEMAP_PATHS = [
    "/",
    "/how-it-works",
    "/for-coding-tools",
    "/guides",
    *[f"/guides/{slug}" for slug in GUIDES],
]

# Paths that keep the plain JSON 404 — form/API consumers expect it. Any
# other unknown path renders the branded HTML 404 page instead.
_JSON_404_PREFIXES = ("/api/", "/f/", "/manage/", "/verify/", "/healthz")


@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException) -> Response:
    if request.url.path.startswith(_JSON_404_PREFIXES):
        return JSONResponse({"detail": exc.detail}, status_code=404)
    return HTMLResponse(
        render("404.html", settings=get_settings(request)), status_code=404
    )


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots_txt(settings: Settings = Depends(get_settings)) -> str:
    base = settings.base_url.rstrip("/")
    return "\n".join(
        [
            "User-agent: *",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /manage/",
            "Disallow: /verify/",
            "Disallow: /f/",
            "Disallow: /healthz",
            "",
            "# OAI-SearchBot indexes pages for ChatGPT search — explicitly welcome",
            "# on the public pages (same restrictions as every other crawler).",
            "User-agent: OAI-SearchBot",
            "Allow: /",
            "Disallow: /api/",
            "Disallow: /manage/",
            "Disallow: /verify/",
            "Disallow: /f/",
            "Disallow: /healthz",
            "",
            f"Sitemap: {base}/sitemap.xml",
            "",
        ]
    )


@app.get("/sitemap.xml")
def sitemap_xml(settings: Settings = Depends(get_settings)) -> Response:
    base = settings.base_url.rstrip("/")
    urls = "\n".join(f"  <url><loc>{base}{path}</loc></url>" for path in SITEMAP_PATHS)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls}\n</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/", response_class=HTMLResponse)
def index(settings: Settings = Depends(get_settings)) -> str:
    return render(
        "index.html",
        settings=settings,
        canonical_path="/",
        guides=GUIDES,
    )


@app.get("/how-it-works", response_class=HTMLResponse)
def how_it_works(settings: Settings = Depends(get_settings)) -> str:
    return render(
        "how-it-works.html",
        settings=settings,
        canonical_path="/how-it-works",
    )


@app.get("/guides", response_class=HTMLResponse)
def guides_index(settings: Settings = Depends(get_settings)) -> str:
    return render(
        "guides.html",
        settings=settings,
        canonical_path="/guides",
        guides=GUIDES,
    )


@app.get("/guides/{slug}", response_class=HTMLResponse)
def guide_page(slug: str, settings: Settings = Depends(get_settings)) -> HTMLResponse:
    guide = GUIDES.get(slug)
    if guide is None:
        raise HTTPException(status_code=404, detail="Guide not found")
    return HTMLResponse(
        render(
            guide["template"],
            settings=settings,
            canonical_path=f"/guides/{slug}",
            guide={"slug": slug, **guide},
        )
    )


@app.get("/manage/{manage_token}", response_class=HTMLResponse)
async def manage_page(
    manage_token: str,
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> HTMLResponse:
    endpoint = await svc.find_by_manage_token(store, manage_token)
    if endpoint is None:
        return HTMLResponse(
            render("manage.html", settings=settings, found=False), status_code=404
        )
    return HTMLResponse(
        render(
            "manage.html",
            settings=settings,
            found=True,
            manage_token=manage_token,
            status=svc.to_status(endpoint),
        )
    )
