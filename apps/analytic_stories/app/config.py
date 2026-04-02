import os

DB_PATH = os.getenv("DB_PATH", "/data/analytic_stories.db")
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8080"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "info")
