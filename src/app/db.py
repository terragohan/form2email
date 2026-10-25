from fastapi import Request


def get_store(request: Request):
    env = request.scope.get("env")
    if env is None or getattr(env, "DB", None) is None:
        raise RuntimeError("Cloudflare DB binding is not configured")

    from app.store.d1 import D1Store

    yield D1Store(env.DB)
