import hashlib
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_STATIC_DIR = Path(__file__).parent / "static"

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(),
)

# Content-hash cache buster for static assets: referenced as ?v= in templates
# so a CSS/asset change yields a new URL and edge caches (4h TTL) never serve
# stale assets for fresh HTML.
_env.globals["static_version"] = hashlib.sha256(
    (_STATIC_DIR / "style.css").read_bytes()
).hexdigest()[:12]


def render(template: str, **context) -> str:
    return _env.get_template(template).render(**context)
