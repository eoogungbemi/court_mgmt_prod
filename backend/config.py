from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

BASE_DIR = Path(__file__).parent

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://court:court@localhost:5432/court_mgmt",
)

# ── Auth ──────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# ── Runtime ───────────────────────────────────────────────────────────────────
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")  # development | production

# Comma-separated list of allowed CORS origins
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# ── Seed / admin bootstrap ────────────────────────────────────────────────────
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme")

# ── Cache ─────────────────────────────────────────────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ── Observability ─────────────────────────────────────────────────────────────
SENTRY_DSN = os.getenv("SENTRY_DSN", "")

# ── AI ────────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "court-mgmt-prod")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

# ── Court configuration ───────────────────────────────────────────────────────
NUM_COURTROOMS = 20
NUM_LAWYERS = 40
COURT_START_HOUR = 9
COURT_END_HOUR = 17
BUFFER_BETWEEN_HEARINGS_MINS = 10
MAX_LAWYER_HEARINGS_PER_DAY = 8

# Hearing types and duration ranges (minutes) — Allegheny County Juvenile Court.
HEARING_DURATIONS: dict[str, dict[str, tuple[int, int]]] = {
    "delinquency": {
        "detention_hearing":     (15, 30),
        "adjudicatory_hearing":  (30, 90),
        "dispositional_hearing": (20, 45),
        "review_hearing":        (15, 30),
        "transfer_hearing":      (45, 120),
        "motion_hearing":        (20, 45),
        "competency_hearing":    (30, 60),
    },
    "dependency": {
        "shelter_care_hearing":  (15, 30),
        "adjudicatory_hearing":  (30, 90),
        "dispositional_hearing": (20, 45),
        "permanency_hearing":    (30, 60),
        "review_hearing":        (15, 30),
        "motion_hearing":        (20, 45),
    },
    "status_offense": {
        "intake_conference":     (15, 30),
        "adjudicatory_hearing":  (20, 45),
        "dispositional_hearing": (15, 30),
        "review_hearing":        (15, 30),
    },
}

COMPLEXITY_MULTIPLIER: dict[str, float] = {
    "low": 0.8,
    "medium": 1.0,
    "high": 1.5,
}
