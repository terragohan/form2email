"""AWS Lambda entrypoint — Mangum adapts the FastAPI ASGI app to Lambda."""

from mangum import Mangum

from app.main import app

handler = Mangum(app)
