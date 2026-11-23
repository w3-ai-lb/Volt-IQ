"""
Application Layer entry point.

AI-Powered Energy Analytics and Customer Engagement Platform
NXTTRN x MUBS: Industry Internship

Run locally:
    uvicorn app.main:app --reload
Interactive API docs:
    http://localhost:8000/docs
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import create_all_tables
from app.routers import (
    ai,
    ask,
    analytics,
    auth,
    billing,
    chat,
    consumption,
    crm,
    dashboard,
    ishtirak,
    preferences,
    reports,
    search,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.API_VERSION,
    description=(
        "REST API for the AI-Powered Energy Analytics and Customer Engagement "
        "Platform. Implements the Application Layer of the three-tier "
        "architecture: authentication, business logic, AI services and "
        "database communication."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
)

# --- CORS -------------------------------------------------------------------
# Allows the React frontend (Vite dev server, and later the Vercel domain)
# to call this API from the browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Routers ----------------------------------------------------------------
app.include_router(auth.router)
app.include_router(billing.router)
app.include_router(consumption.router)
app.include_router(analytics.router)
app.include_router(dashboard.router)
app.include_router(ai.router)
app.include_router(chat.router)
app.include_router(reports.router)
app.include_router(search.router)
app.include_router(preferences.router)
app.include_router(ishtirak.router)
app.include_router(ask.router)
app.include_router(crm.router)


# --- Lifecycle --------------------------------------------------------------
def check_jwt_secret() -> None:
    """
    Refuse to serve a real database with a signing key anybody can read.

    The default in app/config.py and the example in .env.example are public:
    with either one, anyone who has seen the repository could sign a token for
    any account, administrators included. On anything but SQLite the server
    does not start. On SQLite, a local development database, it starts and
    says so in the log, so a fresh clone still runs without setup.
    """
    problem = settings.jwt_secret_problem
    if problem is None:
        return
    message = (
        f"JWT_SECRET_KEY is not safe to use: {problem}. Set a long random value in "
        "backend/.env (or in the service's environment), for example the output of: "
        'python -c "import secrets; print(secrets.token_urlsafe(48))"'
    )
    if settings.is_sqlite:
        logger.warning("%s. Allowed only because the database is a local SQLite file.", message)
        return
    raise RuntimeError(message)


def seed_demo_if_empty() -> None:
    """Fill an empty database with demo data, only when SEED_DEMO_DATA_ON_EMPTY_DB is true."""
    if not settings.SEED_DEMO_DATA_ON_EMPTY_DB:
        return
    from app.database import SessionLocal
    from app.models.customer import Customer
    from app.pipeline.seed import seed

    with SessionLocal() as db:
        if db.query(Customer).first() is not None:
            return
        logger.warning("Empty database and SEED_DEMO_DATA_ON_EMPTY_DB=true: loading the demo data")
        seed(db)


@app.on_event("startup")
def on_startup() -> None:
    """Create any missing tables so a fresh clone runs without a manual step."""
    check_jwt_secret()
    create_all_tables()
    seed_demo_if_empty()
    engine_name = "PostgreSQL" if not settings.is_sqlite else "SQLite (development)"
    logger.info("Database ready, %s", engine_name)
    if settings.RETURN_RESET_TOKEN_IN_RESPONSE and not settings.is_sqlite:
        logger.warning(
            "RETURN_RESET_TOKEN_IN_RESPONSE is true but the database is not SQLite, so the "
            "setting is ignored: password-reset tokens are never returned in API responses "
            "outside a local demo database. Set it to false in this environment."
        )
    logger.info("API docs available at /docs")


# --- Error handling ---------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Return a readable message instead of the raw pydantic error tree."""
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(part) for part in first.get("loc", []) if part != "body")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": f"{field}: {first.get('msg', 'Invalid input')}" if field
            else first.get("msg", "Invalid input"),
        },
    )


# --- Health / meta ----------------------------------------------------------
@app.get("/", tags=["Health"])
def root() -> dict:
    return {
        "name": settings.PROJECT_NAME,
        "version": settings.API_VERSION,
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
def health() -> dict:
    """Liveness probe, used by Render to confirm the service is up."""
    return {"status": "healthy"}
