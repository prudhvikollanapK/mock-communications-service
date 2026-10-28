import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/communications",
)
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
API_KEYS = {
    item.strip()
    for item in os.getenv("API_KEYS", "dev-key").split(",")
    if item.strip()
}
DEFAULT_CONCURRENT_LIMIT = int(os.getenv("CONCURRENT_CALL_LIMIT", "3"))
DEFAULT_CPS_LIMIT = int(os.getenv("CPS_LIMIT", "2"))
CALL_MIN_DELAY = float(os.getenv("CALL_MIN_DELAY", "1"))
CALL_MAX_DELAY = float(os.getenv("CALL_MAX_DELAY", "3"))
RECORDING_DIR = os.getenv("RECORDING_DIR", "/recordings")
