from __future__ import annotations

import json
import math
import os
import re
import secrets
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
store_lock = Lock()
FRONTEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
USER_DATA_DIR = DATA_DIR / "users"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
OLLAMA_TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT_SEC", "90"))
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "5000"))

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_TIME_DECAY_DAYS = int(os.getenv("RAG_TIME_DECAY_DAYS", "30"))
RAG_MIN_CONFIDENCE = float(os.getenv("RAG_MIN_CONFIDENCE", "0.08"))

ESTIMATE_MIN = 15
ESTIMATE_MAX = 240

WEEK_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEKDAY_TO_KEY = {0: "mon", 1: "tue", 2: "wed", 3: "thu", 4: "fri", 5: "sat", 6: "sun"}
WEEK_LABELS = {
    "mon": "周一",
    "tue": "周二",
    "wed": "周三",
    "thu": "周四",
    "fri": "周五",
    "sat": "周六",
    "sun": "周日",
}

users_db: dict[str, dict[str, str]] = {}
sessions: dict[str, str] = {}


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d")


def current_week_key() -> str:
    return WEEKDAY_TO_KEY[datetime.now().weekday()]


def week_key_from_date_str(date_str: str) -> str:
    return WEEKDAY_TO_KEY[parse_date(date_str).weekday()]


def format_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def iter_dates(start_dt: datetime, end_dt: datetime):
    cursor = datetime(start_dt.year, start_dt.month, start_dt.day)
    stop = datetime(end_dt.year, end_dt.month, end_dt.day)
    while cursor <= stop:
        yield cursor
        cursor = cursor + timedelta(days=1)


def parse_hhmm_to_minutes(value: str) -> int:
    if not re.match(r"^\d{2}:\d{2}$", value):
        raise ValueError("时间格式必须是 HH:MM")
    hour, minute = value.split(":")
    h = int(hour)
    m = int(minute)
    if h < 0 or h > 23 or m < 0 or m > 59:
        raise ValueError("时间必须在 00:00 到 23:59")
    return h * 60 + m


def minutes_to_hhmm(minutes: int) -> str:
    m = max(0, min(minutes, 24 * 60))
    h = m // 60
    mm = m % 60
    return f"{h:02d}:{mm:02d}"


def clamp_minutes(value: int) -> int:
    return max(ESTIMATE_MIN, min(value, ESTIMATE_MAX))


def tokenize_title(text: str) -> set[str]:
    parts = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", str(text).lower())
    return set(parts)


def normalize_and_validate_availability(payload: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    normalized: dict[str, list[dict[str, str]]] = {}
    for key in WEEK_KEYS:
        day_ranges = payload.get(key, [])
        if not isinstance(day_ranges, list):
            raise ValueError(f"{WEEK_LABELS[key]} 必须是数组")
        parsed: list[tuple[int, int]] = []
        for item in day_ranges:
            if not isinstance(item, dict):
                raise ValueError(f"{WEEK_LABELS[key]} 的每个时段必须是对象")
            start = str(item.get("start", "")).strip()
            end = str(item.get("end", "")).strip()
            if not start or not end:
                raise ValueError(f"{WEEK_LABELS[key]} 时段必须包含 start 和 end")
            s = parse_hhmm_to_minutes(start)
            e = parse_hhmm_to_minutes(end)
            if e <= s:
                raise ValueError(f"{WEEK_LABELS[key]} 存在结束早于开始的时段")
            parsed.append((s, e))
        parsed.sort(key=lambda x: x[0])
        for i in range(1, len(parsed)):
            if parsed[i][0] < parsed[i - 1][1]:
                raise ValueError(f"{WEEK_LABELS[key]} 存在重叠时段")
        normalized[key] = [{"start": minutes_to_hhmm(s), "end": minutes_to_hhmm(e)} for s, e in parsed]
    return normalized


def default_user_state() -> dict[str, Any]:
    return {
        "tasks": [],
        "todayPlan": None,
        "plansByDate": {},
        "checkins": [],
        "lastPlanner": "none",
        "weeklyAvailability": {key: [] for key in WEEK_KEYS},
    }


def safe_username(username: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", username)


def user_state_file(username: str) -> Path:
    return USER_DATA_DIR / f"{safe_username(username)}_state.json"


def user_rag_file(username: str) -> Path:
    return USER_DATA_DIR / f"{safe_username(username)}_rag_samples.jsonl"


def save_users() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users_db, ensure_ascii=False, indent=2), encoding="utf-8")


def load_users() -> None:
    global users_db
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not USERS_FILE.exists():
        users_db = {}
        return
    try:
        raw = json.loads(USERS_FILE.read_text(encoding="utf-8"))
        users_db = raw if isinstance(raw, dict) else {}
    except Exception:
        users_db = {}


def hash_password(password: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{password}".encode("utf-8")).hexdigest()


def load_user_state(username: str) -> dict[str, Any]:
    path = user_state_file(username)
    if not path.exists():
        return default_user_state()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return default_user_state()
        state = default_user_state()
        state.update(raw)
        state["weeklyAvailability"] = normalize_and_validate_availability(state.get("weeklyAvailability", {}))
        if not isinstance(state.get("plansByDate"), dict):
            state["plansByDate"] = {}
        if not isinstance(state.get("tasks"), list):
            state["tasks"] = []
        if not isinstance(state.get("checkins"), list):
            state["checkins"] = []
        return state
    except Exception:
        return default_user_state()


def save_user_state(username: str, state: dict[str, Any]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    user_state_file(username).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_rag_samples(username: str) -> list[dict[str, Any]]:
    path = user_rag_file(username)
    if not path.exists():
        return []
    samples = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                samples.append(obj)
        except Exception:
            continue
    return samples


def append_rag_sample(username: str, sample: dict[str, Any]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with user_rag_file(username).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(sample, ensure_ascii=False) + "\n")


def get_current_username() -> str | None:
    auth = request.headers.get("Authorization", "").strip()
    token = ""
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
    if not token:
        token = request.headers.get("X-Auth-Token", "").strip()
    if not token:
        return None
    return sessions.get(token)


def build_rag_sample_from_checkin(task: dict[str, Any], checkin: dict[str, Any]) -> dict[str, Any] | None:
    actual = checkin.get("actualMinutes")
    if not checkin.get("done") or actual is None:
        return None
    try:
        actual = int(actual)
    except Exception:
        return None
    if actual <= 0:
        return None
    return {
        "sample_id": str(uuid4()),
        "task_id": task.get("id"),
        "task_title": task.get("title", ""),
        "task_tokens": sorted(tokenize_title(task.get("title", ""))),
        "actual_minutes": actual,
        "estimated_minutes": int(task.get("estimatedMinutes") or 0),
        "completed": True,
        "created_at": checkin.get("checkedAt") or iso_now(),
        "subject_tag": "",
        "difficulty_tag": "",
    }


def robust_median(values: list[int]) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    n = len(vals)
    mid = n // 2
    if n % 2 == 1:
        return float(vals[mid])
    return (vals[mid - 1] + vals[mid]) / 2.0


def robust_mad(values: list[int], med: float) -> float:
    if not values:
        return 0.0
    deviations = [abs(v - med) for v in values]
    return robust_median([int(x) for x in deviations]) or 1.0


def days_since(iso_value: str) -> float:
    try:
        dt = datetime.fromisoformat(iso_value)
    except Exception:
        return 3650.0
    return max(0.0, (datetime.now() - dt).total_seconds() / 86400.0)


def compute_rag_examples(task_title: str, all_samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = tokenize_title(task_title)
    completed_samples = [s for s in all_samples if s.get("completed")]
    actuals = []
    for s in completed_samples:
        try:
            actuals.append(int(s.get("actual_minutes", 0)))
        except Exception:
            continue
    med = robust_median(actuals)
    mad = robust_mad(actuals, med) if actuals else 1.0

    scored = []
    for sample in completed_samples:
        stokens = set(sample.get("task_tokens") or tokenize_title(sample.get("task_title", "")))
        union = tokens | stokens
        text_score = 0.0 if not union else len(tokens & stokens) / len(union)
        actual = int(sample.get("actual_minutes", 0) or 0)
        if actual <= 0:
            continue
        z = abs(actual - med) / (mad * 1.4826) if mad > 0 else 0.0
        reliability = 0.3 if z > 3 else 1.0
        age_days = days_since(str(sample.get("created_at", "")))
        decay = math.exp(-age_days / max(1, RAG_TIME_DECAY_DAYS))
        score = text_score * 0.6 + reliability * 0.25 + decay * 0.15
        if score < RAG_MIN_CONFIDENCE:
            continue
        scored.append(
            {
                "sample_id": sample.get("sample_id"),
                "task_title": sample.get("task_title", ""),
                "actual_minutes": actual,
                "estimated_minutes": int(sample.get("estimated_minutes", 0) or 0),
                "created_at": sample.get("created_at", ""),
                "score": round(score, 4),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(0, RAG_TOP_K)]


def summarize_examples(examples: list[dict[str, Any]]) -> dict[str, float]:
    if not examples:
        return {"count": 0, "mean": 0, "median": 0, "p75": 0}
    vals = sorted(int(e["actual_minutes"]) for e in examples)
    n = len(vals)
    mean = round(sum(vals) / n)
    median = vals[n // 2] if n % 2 == 1 else round((vals[n // 2 - 1] + vals[n // 2]) / 2)
    p75_index = min(n - 1, max(0, math.ceil(0.75 * n) - 1))
    return {"count": n, "mean": mean, "median": median, "p75": vals[p75_index]}


def fallback_estimate(task: dict[str, Any], examples: list[dict[str, Any]]) -> tuple[int, str]:
    user_est = int(task.get("estimatedMinutes") or 0)
    stats = summarize_examples(examples)
    if stats["count"] > 0 and user_est > 0:
        mixed = round(user_est * 0.6 + stats["median"] * 0.4)
        return clamp_minutes(mixed), f"用户预估({user_est}) + 历史中位数({stats['median']})融合"
    if stats["count"] > 0:
        return clamp_minutes(int(stats["median"])), f"基于历史样本中位数({stats['median']})"
    if user_est > 0:
        return clamp_minutes(user_est), f"基于用户预估({user_est})，样本不足"
    return 60, "无样本且无用户预估，采用默认 60 分钟"


def build_llm_prompt_payload(
    tasks: list[dict[str, Any]],
    availability: dict[str, list[dict[str, str]]],
    planning_start: str,
    planning_end: str,
    rag_examples_by_task: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    task_inputs = []
    for task in tasks:
        examples = rag_examples_by_task.get(task["id"], [])
        stats = summarize_examples(examples)
        task_inputs.append(
            {
                "task_id": task["id"],
                "title": task["title"],
                "deadline": task["deadline"],
                "user_estimated_minutes": int(task.get("estimatedMinutes") or 0),
                "rag_examples": examples,
                "rag_stats": stats,
            }
        )
    return {
        "planning_window": {"start_date": planning_start, "end_date": planning_end},
        "available_slots_by_weekday": availability,
        "tasks": task_inputs,
        "user_profile": {"persona": "high_school_student"},
        "constraints": {
            "priority_order": "deadline > slot_fit > history_speed",
            "deadline_rule": "each task can be split across multiple days but must be scheduled no later than its deadline",
            "estimate_range_minutes": [ESTIMATE_MIN, ESTIMATE_MAX],
            "must_return_json": True,
        },
        "output_schema": {
            "task_order": ["task_id"],
            "task_estimates": [
                {
                    "task_id": "string",
                    "estimated_minutes": "int",
                    "evidence_ids": ["sample_id"],
                    "reason": "string",
                }
            ],
            "risks": ["string"],
            "notes": "string",
        },
    }


def ollama_model_ready() -> tuple[bool, str]:
    req = Request(f"{OLLAMA_HOST}/api/tags", method="GET")
    try:
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        return False, f"cannot connect to Ollama: {exc}"
    except Exception as exc:
        return False, f"Ollama check failed: {exc}"
    names = {model.get("name") for model in data.get("models", [])}
    if OLLAMA_MODEL not in names:
        return False, f"model not found: {OLLAMA_MODEL}"
    return True, "ready"


def ollama_chat(payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"{OLLAMA_HOST}/api/chat",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Ollama HTTP error: {exc.code}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT_SEC}s") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT_SEC}s") from exc
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned non-JSON response") from exc


def parse_llm_plan(
    tasks: list[dict[str, Any]],
    llm_json: dict[str, Any],
    rag_examples_by_task: dict[str, list[dict[str, Any]]],
) -> tuple[list[str], dict[str, dict[str, Any]], list[str], str]:
    allowed = {t["id"] for t in tasks}
    raw_order = llm_json.get("task_order", [])
    if not isinstance(raw_order, list):
        raw_order = []
    order = [tid for tid in raw_order if isinstance(tid, str) and tid in allowed]
    if not order:
        order = [t["id"] for t in sorted(tasks, key=lambda x: x["deadline"])]

    estimates_map: dict[str, dict[str, Any]] = {}
    raw_estimates = llm_json.get("task_estimates", [])
    if isinstance(raw_estimates, list):
        for item in raw_estimates:
            if not isinstance(item, dict):
                continue
            tid = item.get("task_id")
            if tid not in allowed:
                continue
            est = item.get("estimated_minutes")
            if not isinstance(est, int):
                continue
            evidence_ids = item.get("evidence_ids", [])
            if not isinstance(evidence_ids, list):
                evidence_ids = []
            valid_ids = {e["sample_id"] for e in rag_examples_by_task.get(tid, [])}
            evidence_ids = [eid for eid in evidence_ids if isinstance(eid, str) and eid in valid_ids]
            reason = str(item.get("reason", "")).strip() or "模型未提供原因，使用回退策略补全"
            estimates_map[tid] = {
                "estimated_minutes": clamp_minutes(est),
                "evidence_ids": evidence_ids,
                "reason": reason,
            }

    risks = llm_json.get("risks", [])
    if not isinstance(risks, list):
        risks = []
    risks = [str(r) for r in risks if str(r).strip()]
    notes = str(llm_json.get("notes", "")).strip()
    return order, estimates_map, risks, notes


def build_day_segments(
    availability: dict[str, list[dict[str, str]]],
    start_dt: datetime,
    end_dt: datetime,
) -> dict[str, list[list[int]]]:
    by_date: dict[str, list[list[int]]] = {}
    for dt in iter_dates(start_dt, end_dt):
        date_str = format_date(dt)
        day_key = WEEKDAY_TO_KEY[dt.weekday()]
        day_slots = availability.get(day_key, [])
        segments: list[list[int]] = []
        for slot in day_slots:
            s = parse_hhmm_to_minutes(slot["start"])
            e = parse_hhmm_to_minutes(slot["end"])
            if e > s:
                segments.append([s, e])
        by_date[date_str] = segments
    return by_date


def schedule_tasks_until_deadline(
    prioritized_task_ids: list[str],
    id_to_task: dict[str, dict[str, Any]],
    estimated_minutes_by_id: dict[str, int],
    segments_by_date: dict[str, list[list[int]]],
    planning_start: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    ordered_dates = sorted(segments_by_date.keys())

    scheduled_blocks: list[dict[str, Any]] = []
    unscheduled_ids: list[str] = []

    for task_id in prioritized_task_ids:
        task = id_to_task.get(task_id)
        if not task:
            continue
        remain = estimated_minutes_by_id.get(task_id, 60)
        deadline_dt = parse_date(task.get("deadline", today_str()))
        horizon_end = max(planning_start, deadline_dt)
        for date_str in ordered_dates:
            if remain <= 0:
                break
            date_dt = parse_date(date_str)
            if date_dt < planning_start or date_dt > horizon_end:
                continue
            segments = segments_by_date.get(date_str, [])
            for seg in segments:
                if remain <= 0:
                    break
                free = seg[1] - seg[0]
                if free <= 0:
                    continue
                allocate = min(free, remain)
                start = seg[0]
                end = start + allocate
                seg[0] = end
                remain -= allocate
                scheduled_blocks.append(
                    {
                        "date": date_str,
                        "taskId": task_id,
                        "startMinute": start,
                        "endMinute": end,
                        "title": task.get("title", ""),
                        "deadline": task.get("deadline", ""),
                    }
                )
        if remain > 0:
            unscheduled_ids.append(task_id)

    return scheduled_blocks, unscheduled_ids


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Auth-Token"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.route("/api/<path:unused>", methods=["OPTIONS"])
def options_handler(unused: str):
    return ("", 204)


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/styles.css", methods=["GET"])
def styles():
    return send_from_directory(FRONTEND_DIR, "styles.css")


@app.route("/app.js", methods=["GET"])
def script():
    return send_from_directory(FRONTEND_DIR, "app.js")


@app.route("/assets/<path:filename>", methods=["GET"])
def assets(filename: str):
    return send_from_directory(FRONTEND_DIR / "assets", filename)


@app.route("/api/health", methods=["GET"])
def health():
    ok, msg = ollama_model_ready()
    return jsonify(
        {
            "ok": True,
            "time": iso_now(),
            "ollamaHost": OLLAMA_HOST,
            "ollamaModel": OLLAMA_MODEL,
            "ollamaModelReady": ok,
            "ollamaMessage": msg,
            "ollamaTimeoutSec": OLLAMA_TIMEOUT_SEC,
            "ragTopK": RAG_TOP_K,
            "ragTimeDecayDays": RAG_TIME_DECAY_DAYS,
            "ragMinConfidence": RAG_MIN_CONFIDENCE,
        }
    )


@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not re.match(r"^[a-zA-Z0-9_-]{3,32}$", username):
        return jsonify({"message": "username must be 3-32 chars: letters/numbers/_/-"}), 400
    if len(password) < 6:
        return jsonify({"message": "password must be at least 6 chars"}), 400

    with store_lock:
        if username in users_db:
            return jsonify({"message": "username already exists"}), 409
        salt = secrets.token_hex(8)
        users_db[username] = {
            "salt": salt,
            "password_hash": hash_password(password, salt),
            "created_at": iso_now(),
        }
        save_users()
        save_user_state(username, default_user_state())
        token = secrets.token_urlsafe(32)
        sessions[token] = username
    return jsonify({"ok": True, "user": {"username": username}, "token": token})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    with store_lock:
        user = users_db.get(username)
        if not user:
            return jsonify({"message": "invalid username or password"}), 401
        expected = hash_password(password, user.get("salt", ""))
        if expected != user.get("password_hash"):
            return jsonify({"message": "invalid username or password"}), 401
        token = secrets.token_urlsafe(32)
        sessions[token] = username
    return jsonify({"ok": True, "user": {"username": username}, "token": token})


@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    auth = request.headers.get("Authorization", "").strip()
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else request.headers.get("X-Auth-Token", "").strip()
    with store_lock:
        if token and token in sessions:
            sessions.pop(token, None)
    return jsonify({"ok": True})


@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    return jsonify({"ok": True, "user": {"username": username}})


@app.route("/api/state", methods=["GET"])
def get_state():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    with store_lock:
        state = load_user_state(username)
    return jsonify(
        {
            "tasks": state["tasks"],
            "todayPlan": state["todayPlan"],
            "checkins": state["checkins"],
            "planner": state["lastPlanner"],
            "weeklyAvailability": state["weeklyAvailability"],
            "user": {"username": username},
        }
    )


@app.route("/api/state/reset", methods=["POST"])
def reset_state():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    with store_lock:
        save_user_state(username, default_user_state())
    return jsonify({"ok": True})


@app.route("/api/settings/availability", methods=["GET"])
def get_availability():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    with store_lock:
        state = load_user_state(username)
    return jsonify({"weeklyAvailability": state["weeklyAvailability"]})


@app.route("/api/settings/availability", methods=["POST"])
def save_availability():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        normalized = normalize_and_validate_availability(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    with store_lock:
        state = load_user_state(username)
        state["weeklyAvailability"] = normalized
        save_user_state(username, state)
    return jsonify({"ok": True, "weeklyAvailability": normalized})


@app.route("/api/tasks", methods=["POST"])
def create_task():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    deadline = str(payload.get("deadline") or "").strip()
    estimated = payload.get("estimatedMinutes")

    if not title or not deadline:
        return jsonify({"message": "title and deadline are required"}), 400
    try:
        parse_date(deadline)
    except ValueError:
        return jsonify({"message": "deadline must be YYYY-MM-DD"}), 400
    if estimated is not None:
        try:
            estimated = int(estimated)
        except (TypeError, ValueError):
            return jsonify({"message": "estimatedMinutes must be an integer"}), 400
        if estimated <= 0:
            return jsonify({"message": "estimatedMinutes must be > 0"}), 400

    task = {
        "id": str(uuid4()),
        "title": title,
        "deadline": deadline,
        "estimatedMinutes": estimated,
        "status": "todo",
    }
    with store_lock:
        state = load_user_state(username)
        state["tasks"].append(task)
        save_user_state(username, state)
    return jsonify(task), 201


@app.route("/api/plans/generate", methods=["POST"])
def generate_plan_for_date():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    req_payload = request.get_json(silent=True) or {}
    target_date = str(req_payload.get("date") or today_str()).strip()
    try:
        planning_start_dt = parse_date(target_date)
    except ValueError:
        return jsonify({"message": "date must be YYYY-MM-DD"}), 400

    with store_lock:
        state = load_user_state(username)
        tasks = [task for task in state["tasks"] if task["status"] != "done"]
        availability = state["weeklyAvailability"]

    if not tasks:
        return jsonify({"message": "请先添加至少一个任务，再生成计划"}), 400

    max_deadline_dt = max(parse_date(task["deadline"]) for task in tasks)
    planning_end_dt = max(planning_start_dt, max_deadline_dt)
    planning_start = format_date(planning_start_dt)
    planning_end = format_date(planning_end_dt)

    segments_by_date = build_day_segments(availability, planning_start_dt, planning_end_dt)
    total_slot_minutes = sum(max(0, e - s) for segs in segments_by_date.values() for s, e in segs)
    if total_slot_minutes <= 0:
        return jsonify({"message": "从今天到任务DDL前都没有可用空闲时段，请先在设置中配置"}), 400

    ok, model_msg = ollama_model_ready()
    if not ok:
        return jsonify({"message": f"Ollama 不可用：{model_msg}"}), 503

    rag_samples = load_rag_samples(username)
    rag_examples_by_task: dict[str, list[dict[str, Any]]] = {}
    for task in tasks:
        rag_examples_by_task[task["id"]] = compute_rag_examples(task["title"], rag_samples)

    prompt_context = build_llm_prompt_payload(tasks, availability, planning_start, planning_end, rag_examples_by_task)
    llm_payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a study planning assistant for constrained scheduling.\n"
                    "Hard rules:\n"
                    "1) Return JSON only, no markdown and no extra text.\n"
                    "2) You must estimate each task duration using rag_examples evidence when available.\n"
                    "3) Priority must follow: deadline > available slot fit > historical completion speed.\n"
                    "4) A task can be split across multiple days, but never scheduled after its deadline.\n"
                    "5) If evidence is insufficient, explicitly state the risk.\n"
                    "6) Output keys exactly: task_order, task_estimates, risks, notes.\n"
                    "7) task_estimates[].evidence_ids must reference rag_examples.sample_id values."
                ),
            },
            {"role": "user", "content": json.dumps(prompt_context, ensure_ascii=False)},
        ],
        "stream": False,
        "format": "json",
    }

    try:
        llm_res = ollama_chat(llm_payload)
        parsed = json.loads(llm_res.get("message", {}).get("content", "{}"))
        order, est_map, llm_risks, llm_notes = parse_llm_plan(tasks, parsed, rag_examples_by_task)
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return jsonify({"message": f"模型响应超时（{OLLAMA_TIMEOUT_SEC} 秒内未返回）"}), 504
        return jsonify({"message": f"模型调用失败：{msg}"}), 502
    except Exception as exc:
        return jsonify({"message": f"模型解析失败：{exc}"}), 502

    estimated_minutes_by_id: dict[str, int] = {}
    estimate_details = []
    for task in tasks:
        task_id = task["id"]
        task_examples = rag_examples_by_task.get(task_id, [])
        if task_id in est_map and est_map[task_id]["evidence_ids"]:
            est_val = clamp_minutes(int(est_map[task_id]["estimated_minutes"]))
            reason = est_map[task_id]["reason"]
            evidence_ids = est_map[task_id]["evidence_ids"]
        else:
            est_val, fallback_reason = fallback_estimate(task, task_examples)
            reason = fallback_reason if task_id not in est_map else f"{est_map[task_id]['reason']}；证据无效已回退"
            evidence_ids = []
        estimated_minutes_by_id[task_id] = est_val
        estimate_details.append(
            {
                "taskId": task_id,
                "title": task["title"],
                "estimatedMinutes": est_val,
                "reason": reason,
                "evidence_ids": evidence_ids,
            }
        )

    id_to_task = {task["id"]: task for task in tasks}
    order = [tid for tid in order if tid in id_to_task]
    missing = [task["id"] for task in sorted(tasks, key=lambda t: t["deadline"]) if task["id"] not in order]
    full_order = order + missing

    scheduled_blocks, unscheduled_ids = schedule_tasks_until_deadline(
        full_order,
        id_to_task,
        estimated_minutes_by_id,
        segments_by_date,
        planning_start_dt,
    )

    total_needed_minutes = sum(estimated_minutes_by_id.values())
    total_scheduled_minutes = sum(blk["endMinute"] - blk["startMinute"] for blk in scheduled_blocks)

    risks = list(llm_risks)
    if unscheduled_ids:
        risks.append("空闲时段不足，部分任务无法在DDL前完成。")
    if total_needed_minutes > total_slot_minutes:
        risks.append(f"总需求 {total_needed_minutes} 分钟，高于可用时段 {total_slot_minutes} 分钟。")
    if total_scheduled_minutes < total_needed_minutes:
        risks.append(f"已安排 {total_scheduled_minutes} / {total_needed_minutes} 分钟，建议压缩任务或增加空闲时段。")
    if not any(rag_examples_by_task.values()):
        risks.append("RAG 样本不足，估时回退比例较高。")

    note = ""
    if unscheduled_ids:
        titles = [id_to_task[tid]["title"] for tid in unscheduled_ids if tid in id_to_task]
        note = f"以下任务未能完全排入DDL前：{', '.join(titles)}"

    rag_examples_flat = []
    for task in tasks:
        rag_examples_flat.append(
            {
                "taskId": task["id"],
                "title": task["title"],
                "examples": rag_examples_by_task.get(task["id"], []),
            }
        )

    details = {
        "rationale": llm_notes or "计划按DDL优先，并允许任务拆分到多个日期，只在用户空闲时段中安排。",
        "risks": risks,
        "taskEstimates": estimate_details,
        "ragTopK": RAG_TOP_K,
        "ragExamples": rag_examples_flat,
        "planningWindow": {"start": planning_start, "end": planning_end},
    }

    blocks_by_date: dict[str, list[dict[str, Any]]] = {}
    for block in scheduled_blocks:
        blocks_by_date.setdefault(block["date"], []).append(block)

    generated_plans: dict[str, dict[str, Any]] = {}
    for dt in iter_dates(planning_start_dt, planning_end_dt):
        date_str = format_date(dt)
        day_blocks = sorted(blocks_by_date.get(date_str, []), key=lambda b: (b["startMinute"], b["taskId"]))
        seen = set()
        day_task_ids = []
        for blk in day_blocks:
            tid = blk["taskId"]
            if tid not in seen:
                day_task_ids.append(tid)
                seen.add(tid)
        generated_plans[date_str] = {
            "date": date_str,
            "taskIds": day_task_ids,
            "totalEstimatedMinutes": sum(b["endMinute"] - b["startMinute"] for b in day_blocks),
            "scheduledBlocks": [
                {
                    "taskId": b["taskId"],
                    "startMinute": b["startMinute"],
                    "endMinute": b["endMinute"],
                    "title": b["title"],
                    "deadline": b["deadline"],
                }
                for b in day_blocks
            ],
            "weekday": WEEKDAY_TO_KEY[dt.weekday()],
            "note": note if date_str == target_date else "",
            "details": details,
        }

    with store_lock:
        state = load_user_state(username)
        state["plansByDate"] = generated_plans
        state["todayPlan"] = generated_plans.get(today_str())
        state["lastPlanner"] = f"ollama:{OLLAMA_MODEL}+rag_top_k={RAG_TOP_K}"
        save_user_state(username, state)

    plan = generated_plans.get(target_date) or {
        "date": target_date,
        "taskIds": [],
        "totalEstimatedMinutes": 0,
        "scheduledBlocks": [],
        "weekday": week_key_from_date_str(target_date),
        "note": note,
        "details": details,
    }
    return jsonify(
        {
            "plan": plan,
            "planner": state["lastPlanner"],
            "planningWindow": {"start": planning_start, "end": planning_end},
        }
    )


@app.route("/api/plans/today", methods=["POST"])
def build_today_plan():
    payload = request.get_json(silent=True) or {}
    payload["date"] = today_str()
    auth_header = request.headers.get("Authorization")
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header
    with app.test_request_context(method="POST", json=payload, headers=headers):
        return generate_plan_for_date()


@app.route("/api/plans/<date_str>", methods=["GET"])
def get_plan_by_date(date_str: str):
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    try:
        parse_date(date_str)
    except ValueError:
        return jsonify({"message": "date must be YYYY-MM-DD"}), 400
    with store_lock:
        state = load_user_state(username)
        plan = state["plansByDate"].get(date_str)
    return jsonify({"plan": plan})


@app.route("/api/checkins", methods=["POST"])
def create_checkin():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("taskId") or "").strip()
    done = bool(payload.get("done", False))
    actual_minutes = payload.get("actualMinutes")

    if not task_id:
        return jsonify({"message": "taskId is required"}), 400
    if actual_minutes is not None:
        try:
            actual_minutes = int(actual_minutes)
        except (TypeError, ValueError):
            return jsonify({"message": "actualMinutes must be an integer"}), 400
        if actual_minutes <= 0:
            return jsonify({"message": "actualMinutes must be > 0"}), 400

    with store_lock:
        state = load_user_state(username)
        task = next((item for item in state["tasks"] if item["id"] == task_id), None)
        if task is None:
            return jsonify({"message": "taskId not found"}), 404
        task["status"] = "done" if done else "todo"
        checkin = {
            "taskId": task_id,
            "done": done,
            "actualMinutes": actual_minutes,
            "checkedAt": iso_now(),
        }
        state["checkins"].insert(0, checkin)
        save_user_state(username, state)

    sample = build_rag_sample_from_checkin(task, checkin)
    if sample is not None:
        append_rag_sample(username, sample)

    return jsonify(checkin), 201


with store_lock:
    load_users()


if __name__ == "__main__":
    app.run(host=APP_HOST, port=APP_PORT, debug=True)
