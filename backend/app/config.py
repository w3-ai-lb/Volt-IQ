"""
Application configuration.

All settings are read from environment variables (see .env.example).
Nothing secret is ever hard-coded here, this satisfies the
"Secure Database Access" requirement of the Security Architecture.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# A shorter signing key can be guessed offline from any token it signed.
MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Project ---
    PROJECT_NAME: str = "AI-Powered Energy Analytics and Customer Engagement Platform"
    API_VERSION: str = "1.0.0"

    # --- Database -------------------------------------------------------
    # Production (per the Software Architecture document) is PostgreSQL:
    #   postgresql+psycopg2://user:password@localhost:5432/energy_analytics
    # The SQLite default lets the project run with zero setup for local
    # development / demos. Switch by editing DATABASE_URL in .env only,
    # no code changes are needed, SQLAlchemy handles both identically.
    DATABASE_URL: str = "sqlite:///./energy_analytics.db"

    # --- Security (JWT) -------------------------------------------------
    # A placeholder. Anyone who has read this file could sign a token for any
    # account with it, so the server refuses to start on a database other than
    # SQLite until a real value is set (see `jwt_secret_problem` and main.py).
    JWT_SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION-use-a-long-random-string"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8  # 8 hours

    # --- Password reset -------------------------------------------------
    PASSWORD_RESET_EXPIRE_MINUTES: int = 30
    # A demonstration shortcut, OFF by default. There is no email provider yet
    # (Architecture Section XI lists email delivery as a future enhancement),
    # so a reset token has no safe way to reach its owner. When this is true
    # AND the database is SQLite, the token is returned in the API response so
    # the flow can be shown on a local demo database. On any other database it
    # is ignored (see `reset_token_in_response`) and startup logs a warning:
    # handing the token to whoever asks lets anyone reset any account,
    # administrators included. Until email delivery exists, customers of a
    # deployed system cannot reset a forgotten password themselves.
    RETURN_RESET_TOKEN_IN_RESPONSE: bool = False

    # --- Account claiming -----------------------------------------------
    # A customer claims portal access with the Customer ID on their bill AND a
    # one-time registration code issued by the provider (printed on the bill or
    # handed over at the office). A code stops working after this many days,
    # and as soon as it has been used once. See app/core/registration_codes.py.
    REGISTRATION_CODE_VALID_DAYS: int = 30

    # --- CORS -----------------------------------------------------------
    # Vite dev server + the deployed Vercel domain.
    CORS_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"

    # --- AI Chatbot -----------------------------------------------------
    # Leave empty to use the built-in rule-based fallback assistant.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- Billing --------------------------------------------------------
    # Price per kWh used ONLY when a dataset has no cost column, and by the
    # recommendation engine when a customer has no cost history to divide.
    #
    # THIS USED TO SAY USD, AND THAT WAS WRONG
    # ----------------------------------------
    # The whole platform was built on `TARIFF_USD_PER_KWH = 0.25` and
    # `CURRENCY = "USD"`, so every amount on every screen carried a dollar
    # sign. The supervisor's data says otherwise, on every row of it: all
    # 5,400 invoices, all 5,229 payments and all 18 tariffs are marked LBP.
    # This is a Lebanese ishtirak billing in Lebanese pounds.
    #
    # The figure below is his own most recent published rate, June 2026, from
    # `tariffs.csv`. It is a FALLBACK and nothing more: the real rate changes
    # every month with the diesel price and travels on the tariff row attached
    # to each invoice. Across his eighteen months it moves between 27,416 and
    # 34,072 LBP/kWh, which is why a single constant cannot be the answer and
    # is used only where there is no invoice to read.
    TARIFF_LBP_PER_KWH: float = 30_981.0
    CURRENCY: str = "LBP"

    # --- Demo behaviour -------------------------------------------------
    # When true, an account created through /auth/register or by an admin is
    # given a generated 12-month meter history.
    #
    # Defaults to FALSE because it is not how the architecture says data
    # arrives. Section XI of the Software Architecture lists "Integrate the
    # platform with real-time smart electricity meters" as a FUTURE
    # enhancement, and Section IV states the AI engine processes "historical
    # customer data": i.e. records loaded in bulk, not invented at signup.
    # Consumption enters the system through app/pipeline/ingest.py (the
    # "data pipeline consolidating consumption, billing and payment data"
    # deliverable), keyed on customer_id.
    #
    # Set to true only when you need a self-populating account for a demo.
    PROVISION_DEMO_DATA: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def reset_token_in_response(self) -> bool:
        """The demonstration shortcut above: honoured only on a local SQLite database."""
        return self.RETURN_RESET_TOKEN_IN_RESPONSE and self.is_sqlite

    @property
    def jwt_secret_problem(self) -> str | None:
        """
        Why JWT_SECRET_KEY must not sign tokens, or None when it is fine.

        Catches the default above and the example in .env.example (both contain
        "change-me", and both are public), and anything too short to resist
        guessing.
        """
        key = self.JWT_SECRET_KEY or ""
        if "change-me" in key.lower():
            return "it is still the placeholder from app/config.py or .env.example"
        if len(key) < MIN_JWT_SECRET_LENGTH:
            return f"it is shorter than {MIN_JWT_SECRET_LENGTH} characters"
        return None


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed only once per process."""
    return Settings()


settings = get_settings()
