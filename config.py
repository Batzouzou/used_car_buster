"""Search criteria, constants, and configuration."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Search Criteria (locked) ---
SEARCH_CRITERIA = {
    "make": "Toyota",
    "model": "iQ",
    "transmission": "automatic",
    "max_price": 5000,
    "max_mileage_km": 150000,
    "min_year": 2009,
}

# --- Reference point: Orly airport ---
ORLY_LAT = 48.7262
ORLY_LON = 2.3652

# --- Distance zones ---
DISTANCE_ZONES = {
    "PRIME":  {"max_km": 20,  "bonus": 15},
    "NEAR":   {"max_km": 30,  "bonus": 8},
    "FAR":    {"max_km": 40,  "bonus": 3},
    "REMOTE": {"max_km": 9999, "bonus": 0},
}

# --- Scoring weights (must sum to 100) ---
SCORING_WEIGHTS = {
    "price": 30,
    "mileage": 20,
    "year": 15,
    "proximity": 15,
    "condition": 10,
    "transmission": 10,
}

# --- Platforms ---
PLATFORMS = ["leboncoin", "lacentrale", "leparking", "autoscout24"]

# --- Cache ---
CACHE_FRESHNESS_HOURS = 4

# --- LLM ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
LLM_MAX_RETRIES = 2

# --- Telegram ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_FRIEND_CHAT_ID = os.getenv("TELEGRAM_FRIEND_CHAT_ID", "")
TELEGRAM_JEROME_CHAT_ID = os.getenv("TELEGRAM_JEROME_CHAT_ID", "")

# --- Scheduler ---
DEFAULT_INTERVAL_HOURS = 4
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 168  # 1 week

# --- Output directory ---
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "_IQ")
