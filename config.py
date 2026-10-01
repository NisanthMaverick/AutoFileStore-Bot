import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

# Read API_ID (supports API_ID or TELEGRAM_API_ID)
raw_api_id = os.environ.get("API_ID") or os.environ.get("TELEGRAM_API_ID") or "0"
try:
    API_ID = int(raw_api_id)
except ValueError:
    API_ID = 0

# Read API_HASH (supports API_HASH or TELEGRAM_API_HASH)
API_HASH = os.environ.get("API_HASH") or os.environ.get("TELEGRAM_API_HASH") or ""

# Read Bot Token (supports MAIN_BOT_TOKEN, BOT_TOKEN, TELEGRAM_BOT_TOKEN, TOKEN)
MAIN_BOT_TOKEN = (
    os.environ.get("MAIN_BOT_TOKEN")
    or os.environ.get("BOT_TOKEN")
    or os.environ.get("TELEGRAM_BOT_TOKEN")
    or os.environ.get("TOKEN")
    or ""
)
BOT_TOKEN = MAIN_BOT_TOKEN

# Read Owner / Admin ID (supports OWNER_ID, ADMIN_ID, ADMIN_IDS, ADMIN_USER_ID)
raw_owner = (
    os.environ.get("OWNER_ID")
    or os.environ.get("ADMIN_ID")
    or os.environ.get("ADMIN_IDS")
    or os.environ.get("ADMIN_USER_ID")
    or "0"
)
if "," in raw_owner:
    raw_owner = raw_owner.split(",")[0].strip()
try:
    OWNER_ID = int(raw_owner)
except ValueError:
    OWNER_ID = 0
ADMIN_ID = OWNER_ID

# Read Database URL
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Dynamically load Subscriptionbot DB URL from sibling directory
SUBSCRIPTION_DATABASE_URL = None
sub_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Subscriptionbot", ".env")
if os.path.exists(sub_env_path):
    try:
        with open(sub_env_path, "r") as f:
            for line in f:
                if line.strip().startswith("DATABASE_URL="):
                    SUBSCRIPTION_DATABASE_URL = line.split("=", 1)[1].strip()
                    break
    except Exception as e:
        print(f"Error reading Subscriptionbot .env: {e}")

if not SUBSCRIPTION_DATABASE_URL:
    SUBSCRIPTION_DATABASE_URL = os.environ.get(
        "SUBSCRIPTION_DATABASE_URL",
        "postgres://8904fee01839447f7293e1a5041971eb5fbb3491c0259870a575cdc82998f254:sk_M1lCUhXr98UoFzqWJ8ud6@pooled.db.prisma.io:5432/postgres?sslmode=require"
    )

if SUBSCRIPTION_DATABASE_URL.startswith("postgres://"):
    SUBSCRIPTION_DATABASE_URL = SUBSCRIPTION_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Detailed validation check with informative error message listing missing variables
missing_vars = []
if not API_ID:
    missing_vars.append("API_ID / TELEGRAM_API_ID")
if not API_HASH:
    missing_vars.append("API_HASH / TELEGRAM_API_HASH")
if not MAIN_BOT_TOKEN:
    missing_vars.append("MAIN_BOT_TOKEN / BOT_TOKEN / TELEGRAM_BOT_TOKEN")
if not OWNER_ID:
    missing_vars.append("OWNER_ID / ADMIN_ID / ADMIN_IDS")
if not DATABASE_URL:
    missing_vars.append("DATABASE_URL")

if missing_vars:
    raise ValueError(f"Missing critical configuration in environment variables or .env file: {', '.join(missing_vars)}")

# AI Web Series Automation Settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
WEEKLY_SOURCE_CHANNELS = []
raw_sources = os.environ.get("WEEKLY_SOURCE_CHANNELS", "")
if raw_sources:
    for item in raw_sources.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            WEEKLY_SOURCE_CHANNELS.append(int(item))
        except ValueError:
            WEEKLY_SOURCE_CHANNELS.append(item)


