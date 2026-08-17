import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
MAIN_BOT_TOKEN = os.environ.get("MAIN_BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", 0))
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

if not API_ID or not API_HASH or not MAIN_BOT_TOKEN or not OWNER_ID or not DATABASE_URL:
    raise ValueError("Missing critical configuration in environment variables or .env file.")

