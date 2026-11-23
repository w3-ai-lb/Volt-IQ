"""
Data Layer, SQLAlchemy engine, session factory and declarative base.

Works unchanged against PostgreSQL (production) and SQLite (local dev);
the only difference is the DATABASE_URL value in .env.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

# SQLite needs check_same_thread=False because FastAPI serves requests
# from a thread pool. PostgreSQL needs no such flag.
connect_args = {"check_same_thread": False} if settings.is_sqlite else {}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,   # drops dead connections instead of erroring
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    """Declarative base shared by every ORM model."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency, yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create any missing tables. Import models first so they register."""
    from app import models  # noqa: F401  (registers all models on Base)

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()


def add_missing_columns() -> None:
    """
    Bring the existing tables up to the current columns, without creating any
    table: the additive step of create_all_tables on its own.

    The server does this every time it starts. The command-line scripts that
    read whole customer records call it first, so they also work on a database
    the current code has not opened yet: otherwise the first one run after an
    update (check-data.bat, purge-demo.bat or check-chatbot.bat) stops with
    "no such column: customers.session_version". Additive only, and it does
    nothing once the columns are there.
    """
    _add_missing_columns()


# Columns introduced after the first release, as {table: {column: DDL type}}.
_LATER_COLUMNS: dict[str, dict[str, str]] = {
    "customers": {
        "theme": "VARCHAR(10) DEFAULT 'light'",
        "language": "VARCHAR(5) DEFAULT 'en'",
        # Added when the CRM project's record shape was adopted. See the note
        # on Customer.gps_lat: placeholders, never a basis for a distance.
        "gps_lat": "FLOAT",
        "gps_lng": "FLOAT",
        # One-time registration codes, see app/core/registration_codes.py.
        "registration_code_hash": "VARCHAR(255)",
        "registration_code_expires_at": "TIMESTAMP",
        # Signs out other devices when the password changes, see app/core/deps.py.
        "session_version": "INTEGER NOT NULL DEFAULT 0",
    },
    # Fields read off the photographs of the live InteliSCADA panel. They are
    # not in the practice export, so a database created before they were added
    # has the tables but not these columns, and create_all() will not add them.
    "generators": {
        "site_name": "VARCHAR(80)",
        "controller_model": "VARCHAR(60)",
    },
    # Columns the unified CRM added to the ishtirak money tables.
    "invoices": {
        "previous_reading": "FLOAT",
        "current_reading": "FLOAT",
        "reading_id": "VARCHAR(20)",
        "issued_by": "VARCHAR(20)",
    },
    "invoice_payments": {
        "receipt_no": "VARCHAR(30)",
        "reference_no": "VARCHAR(60)",
        "notes": "VARCHAR(255)",
    },
    "generator_telemetry": {
        "fuel_delivery_pressure_bar": "FLOAT",
        "intake_manifold_temp_c": "FLOAT",
        "intake_pressure_bar": "FLOAT",
        "battery_voltage": "FLOAT",
        "breaker_state": "VARCHAR(30)",
        "control_mode": "VARCHAR(10)",
        "maintenance_timer_1_h": "FLOAT",
        "maintenance_timer_2_h": "FLOAT",
        "active_alarm_count": "INTEGER",
    },
}


def _add_missing_columns() -> None:
    """
    Add columns that were introduced after a database was first created.

    SQLAlchemy's create_all() only creates missing TABLES, it never alters an
    existing one. Without this, a database seeded before a column was added
    would raise "no such column" on every query touching it, and the only fix
    would be a full re-seed (losing any accounts the user registered).

    Deliberately additive only: it never drops or retypes anything.
    """
    import logging

    from sqlalchemy import inspect, text

    logger = logging.getLogger(__name__)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    for table, columns in _LATER_COLUMNS.items():
        if table not in tables:
            continue  # create_all just made it, with every column present
        existing = {col["name"] for col in inspector.get_columns(table)}
        for column, ddl in columns.items():
            if column in existing:
                continue
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                logger.info("Schema updated: added %s.%s", table, column)
            except Exception as exc:  # pragma: no cover
                logger.warning("Could not add %s.%s: %s", table, column, exc)
