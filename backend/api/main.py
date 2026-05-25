import time
import uuid
import logging
from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from prometheus_fastapi_instrumentator import Instrumentator

from config import (
    ALLOWED_ORIGINS, ENVIRONMENT, SENTRY_DSN,
    LANGSMITH_API_KEY, LANGSMITH_PROJECT, LANGSMITH_TRACING,
)
from utils.logging import configure_logging, request_id_var
from api.limiter import limiter
from api.routes import (
    auth, users, courtrooms, cases,
    hearings, attorneys, conflicts, export, agents, ws, analytics,
)

configure_logging()
logger = logging.getLogger(__name__)

# ── Sentry ────────────────────────────────────────────────────────────────────
if SENTRY_DSN:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=ENVIRONMENT,
        traces_sample_rate=0.2,   # 20 % of requests get a performance trace
        profiles_sample_rate=0.1,
        send_default_pii=False,   # never send PII to Sentry
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    if LANGSMITH_TRACING and LANGSMITH_API_KEY:
        import os
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"]     = LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"]     = LANGSMITH_PROJECT
        logger.info("LangSmith tracing enabled: project=%s", LANGSMITH_PROJECT)
    logger.info("startup: environment=%s sentry=%s", ENVIRONMENT, bool(SENTRY_DSN))
    yield
    logger.info("shutdown")


app = FastAPI(
    title="Allegheny County Juvenile Court — Case Management API",
    description=(
        "Court of Common Pleas of Allegheny County, Family Division — Juvenile Branch. "
        "Pittsburgh, PA."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs"    if ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc"  if ENVIRONMENT != "production" else None,
    openapi_url="/api/openapi.json" if ENVIRONMENT != "production" else None,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

Instrumentator().instrument(app).expose(app, endpoint="/api/metrics", include_in_schema=False)

# ── X-Request-ID middleware ───────────────────────────────────────────────────
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    token  = request_id_var.set(req_id)
    start  = time.perf_counter()
    response = None
    try:
        response = await call_next(request)
        return response
    finally:
        elapsed = round((time.perf_counter() - start) * 1000)
        logger.info(
            "%s %s %s %dms",
            request.method, request.url.path,
            getattr(response, "status_code", "???"),
            elapsed,
        )
        if response is not None:
            response.headers["X-Request-ID"] = req_id
        request_id_var.reset(token)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router,       prefix="/api")
app.include_router(users.router,      prefix="/api")
app.include_router(courtrooms.router, prefix="/api")
app.include_router(cases.router,      prefix="/api")
app.include_router(hearings.router,   prefix="/api")
app.include_router(attorneys.router,  prefix="/api")
app.include_router(conflicts.router,  prefix="/api")
app.include_router(export.router,     prefix="/api")
app.include_router(agents.router,     prefix="/api")
app.include_router(ws.router,         prefix="/api")
app.include_router(analytics.router,  prefix="/api")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"])
def health():
    from sqlalchemy import text
    from db.database import SessionLocal
    import utils.cache as cache

    checks: dict[str, str] = {}

    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
        checks["db"] = "ok"
    except Exception as exc:
        logger.error("health: db check failed: %s", exc)
        checks["db"] = "error"

    try:
        checks["redis"] = "ok" if cache.ping() else "unavailable"
    except Exception as exc:
        logger.error("health: redis check failed: %s", exc)
        checks["redis"] = "error"

    degraded = any(v == "error" for v in checks.values())
    return JSONResponse(
        status_code=503 if degraded else 200,
        content={
            "status": "degraded" if degraded else "ok",
            "service": "court-mgmt-api",
            "environment": ENVIRONMENT,
            "checks": checks,
        },
    )
