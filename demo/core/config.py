import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
# Default to qwen3:4b and keep it stable unless explicitly overridden by user env var.
OLLAMA_MODEL_DEFAULT = os.getenv("OLLAMA_MODEL_DEFAULT", "qwen3:4b")
OLLAMA_MODEL_QUALITY = os.getenv("OLLAMA_MODEL_QUALITY", "qwen3:4b")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", OLLAMA_MODEL_DEFAULT)
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_FAST_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_FAST_TIMEOUT_SECONDS", "12"))
OLLAMA_RETRY_COUNT = int(os.getenv("OLLAMA_RETRY_COUNT", "1"))
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT", "200"))
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "2048"))
OLLAMA_NUM_THREAD = int(os.getenv("OLLAMA_NUM_THREAD", str(max(1, os.cpu_count() or 1))))
PLAN_MAX_DAYS = int(os.getenv("PLAN_MAX_DAYS", "14"))
UI_THEME = os.getenv("UI_THEME", "clean_productive_v1")
APP_TITLE = "J人模拟器"

WEEKDAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

WEEKDAY_LABELS = {
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
}
