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

from knowledge_rag import (
    build_evidence_package,
    clamp_task_minutes,
    evidence_to_rag_examples,
    fallback_estimate_from_package,
    index_knowledge_by_type,
)

app = Flask(__name__)
store_lock = Lock()
FRONTEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
USER_DATA_DIR = DATA_DIR / "users"
KNOWLEDGE_FILE = DATA_DIR / "knowledge" / "task_knowledge_v2.jsonl"
KNOWLEDGE_FILE_LEGACY = DATA_DIR / "knowledge" / "task_duration_knowledge.jsonl"

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
OLLAMA_TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT_SEC", "90"))
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "5000"))

RAG_TOP_K = int(os.getenv("RAG_TOP_K", "5"))
RAG_TIME_DECAY_DAYS = int(os.getenv("RAG_TIME_DECAY_DAYS", "30"))
RAG_MIN_CONFIDENCE = float(os.getenv("RAG_MIN_CONFIDENCE", "0.08"))
P_TYPE_SLOW_MULTIPLIER = float(os.getenv("P_TYPE_SLOW_MULTIPLIER", "1.18"))
ESTIMATE_PERCENTILE = os.getenv("ESTIMATE_PERCENTILE", "p50")

ESTIMATE_MIN = 15
ESTIMATE_MAX = 480

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

SUBJECT_LABELS = {
    "chinese": "语文",
    "math": "数学",
    "english": "英语",
    "physics": "物理",
    "chemistry": "化学",
    "biology": "生物",
    "history": "历史",
    "politics": "政治",
    "geography": "地理",
    "general": "综合/其他",
}

TASK_TYPE_LABELS = {
    "test_paper": "试卷",
    "exercise_set": "习题/刷题",
    "essay": "作文/写作",
    "reading": "阅读",
    "recitation": "背诵",
    "vocabulary": "单词/词组",
    "mistake_review": "错题整理",
    "chapter_review": "章节复习",
    "preview": "预习",
    "lab_report": "实验报告",
    "group_work": "小组作业",
    "presentation": "展示/PPT",
}

DIFFICULTY_LABELS = {
    "easy": "简单",
    "medium": "普通",
    "hard": "困难",
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
    return clamp_task_minutes(value)


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


def load_knowledge_records() -> list[dict[str, Any]]:
    source = KNOWLEDGE_FILE if KNOWLEDGE_FILE.exists() else KNOWLEDGE_FILE_LEGACY
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in source.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        rid = str(obj.get("id") or "").strip()
        if not rid:
            continue
        records.append(obj)
    return records


def append_rag_sample(username: str, sample: dict[str, Any]) -> None:
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with user_rag_file(username).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(sample, ensure_ascii=False) + "\n")


def validate_task_payload(payload: dict[str, Any], partial: bool = False) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    title = str(payload.get("title") or "").strip()
    deadline = str(payload.get("deadline") or "").strip()
    subject = str(payload.get("subject") or "general").strip()
    task_type = str(payload.get("taskType") or "exercise_set").strip()
    difficulty = str(payload.get("difficulty") or "medium").strip()
    estimated = payload.get("estimatedMinutes")

    if not partial or "title" in payload:
        if not title:
            raise ValueError("title is required")
        cleaned["title"] = title
    if not partial or "deadline" in payload:
        if not deadline:
            raise ValueError("deadline is required")
        parse_date(deadline)
        cleaned["deadline"] = deadline
    if not partial or "subject" in payload:
        if subject not in SUBJECT_LABELS:
            raise ValueError("subject is invalid")
        cleaned["subject"] = subject
    if not partial or "taskType" in payload:
        if task_type not in TASK_TYPE_LABELS:
            raise ValueError("taskType is invalid")
        cleaned["taskType"] = task_type
    if not partial or "difficulty" in payload:
        if difficulty not in DIFFICULTY_LABELS:
            raise ValueError("difficulty is invalid")
        cleaned["difficulty"] = difficulty
    if (not partial or "estimatedMinutes" in payload) and estimated is not None:
        try:
            estimated = int(estimated)
        except (TypeError, ValueError):
            raise ValueError("estimatedMinutes must be an integer")
        if estimated <= 0:
            raise ValueError("estimatedMinutes must be > 0")
        cleaned["estimatedMinutes"] = estimated
    elif not partial or "estimatedMinutes" in payload:
        cleaned["estimatedMinutes"] = None
    return cleaned


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
        "subject_tag": task.get("subject", "general"),
        "task_type_tag": task.get("taskType", "exercise_set"),
        "difficulty_tag": task.get("difficulty", "medium"),
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


def estimate_value_from_example(example: dict[str, Any]) -> int:
    for key in ("actual_minutes", "estimated_minutes_p50", "estimated_minutes"):
        try:
            value = int(example.get(key, 0) or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    return 0


def compute_history_rag_examples(task: dict[str, Any], all_samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tokens = tokenize_title(task.get("title", ""))
    subject = task.get("subject", "general")
    task_type = task.get("taskType", "exercise_set")
    difficulty = task.get("difficulty", "medium")
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
        subject_score = 1.0 if sample.get("subject_tag") == subject else 0.0
        type_score = 1.0 if sample.get("task_type_tag") == task_type else 0.0
        difficulty_score = 1.0 if sample.get("difficulty_tag") == difficulty else 0.0
        actual = int(sample.get("actual_minutes", 0) or 0)
        if actual <= 0:
            continue
        z = abs(actual - med) / (mad * 1.4826) if mad > 0 else 0.0
        reliability = 0.3 if z > 3 else 1.0
        age_days = days_since(str(sample.get("created_at", "")))
        decay = math.exp(-age_days / max(1, RAG_TIME_DECAY_DAYS))
        score = (
            text_score * 0.35
            + subject_score * 0.2
            + type_score * 0.18
            + difficulty_score * 0.07
            + reliability * 0.12
            + decay * 0.08
        )
        if score < RAG_MIN_CONFIDENCE:
            continue
        scored.append(
            {
                "sample_id": sample.get("sample_id"),
                "source": "user_history",
                "task_title": sample.get("task_title", ""),
                "actual_minutes": actual,
                "estimated_minutes": int(sample.get("estimated_minutes", 0) or 0),
                "subject": sample.get("subject_tag", "general"),
                "task_type": sample.get("task_type_tag", "exercise_set"),
                "difficulty": sample.get("difficulty_tag", "medium"),
                "created_at": sample.get("created_at", ""),
                "score": round(score, 4),
            }
        )
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[: max(0, RAG_TOP_K)]


def build_task_rag_context(
    task: dict[str, Any],
    history_samples: list[dict[str, Any]],
    knowledge_indexed: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    history_examples = compute_history_rag_examples(task, history_samples)
    package = build_evidence_package(
        task,
        knowledge_indexed,
        p_type_mult=P_TYPE_SLOW_MULTIPLIER,
        estimate_percentile=ESTIMATE_PERCENTILE,
        calibration_top_k=3,
    )
    knowledge_examples = evidence_to_rag_examples(package)
    combined = history_examples + knowledge_examples
    combined.sort(key=lambda x: x.get("score", 0), reverse=True)
    return package, combined[: max(0, RAG_TOP_K)]


def summarize_examples(examples: list[dict[str, Any]]) -> dict[str, float]:
    if not examples:
        return {"count": 0, "mean": 0, "median": 0, "p75": 0}
    vals = sorted(estimate_value_from_example(e) for e in examples if estimate_value_from_example(e) > 0)
    if not vals:
        return {"count": 0, "mean": 0, "median": 0, "p75": 0}
    n = len(vals)
    mean = round(sum(vals) / n)
    median = vals[n // 2] if n % 2 == 1 else round((vals[n // 2 - 1] + vals[n // 2]) / 2)
    p75_index = min(n - 1, max(0, math.ceil(0.75 * n) - 1))
    return {"count": n, "mean": mean, "median": median, "p75": vals[p75_index]}


def fallback_estimate(
    task: dict[str, Any],
    examples: list[dict[str, Any]],
    evidence_package: dict[str, Any] | None = None,
) -> tuple[int, str]:
    history_only = [e for e in examples if e.get("source") == "user_history"]
    return fallback_estimate_from_package(task, evidence_package, history_only, clamp_minutes)


def build_llm_prompt_payload(
    tasks: list[dict[str, Any]],
    availability: dict[str, list[dict[str, str]]],
    planning_start: str,
    planning_end: str,
    rag_examples_by_task: dict[str, list[dict[str, Any]]],
    evidence_packages_by_task: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence_packages_by_task = evidence_packages_by_task or {}
    task_inputs = []
    for task in tasks:
        tid = task["id"]
        examples = rag_examples_by_task.get(tid, [])
        package = evidence_packages_by_task.get(tid, {})
        stats = summarize_examples(examples)
        parametric = package.get("parametric_estimate") or {}
        task_inputs.append(
            {
                "task_id": tid,
                "title": task["title"],
                "deadline": task["deadline"],
                "subject": task.get("subject", "general"),
                "subject_label": SUBJECT_LABELS.get(task.get("subject", "general"), "综合/其他"),
                "task_type": task.get("taskType", "exercise_set"),
                "task_type_label": TASK_TYPE_LABELS.get(task.get("taskType", "exercise_set"), "习题/刷题"),
                "difficulty": task.get("difficulty", "medium"),
                "difficulty_label": DIFFICULTY_LABELS.get(task.get("difficulty", "medium"), "普通"),
                "user_estimated_minutes": int(task.get("estimatedMinutes") or 0),
                "evidence_package": package,
                "parametric_estimate_minutes": parametric.get("picked") or parametric.get("p50"),
                "decomposition_suggestion": package.get("decomposition_suggestion", []),
                "rag_examples": examples,
                "rag_stats": stats,
            }
        )
    return {
        "planning_window": {"start_date": planning_start, "end_date": planning_end},
        "available_slots_by_weekday": availability,
        "tasks": task_inputs,
        "user_profile": {"persona": "p_type_high_school_student", "p_type_slow_multiplier": P_TYPE_SLOW_MULTIPLIER},
        "constraints": {
            "priority_order": "deadline > slot_fit > history_speed",
            "deadline_rule": "each task can be split across multiple days but must be scheduled no later than its deadline",
            "estimate_range_minutes": [ESTIMATE_MIN, ESTIMATE_MAX],
            "estimate_policy": "prefer evidence_package.parametric_estimate; adjust within +/-15% only when justified",
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


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


DAY_NAME_TO_KEY = {
    "mon": "mon",
    "tue": "tue",
    "wed": "wed",
    "thu": "thu",
    "fri": "fri",
    "sat": "sat",
    "sun": "sun",
    "周一": "mon",
    "星期一": "mon",
    "周二": "tue",
    "星期二": "tue",
    "周三": "wed",
    "星期三": "wed",
    "周四": "thu",
    "星期四": "thu",
    "周五": "fri",
    "星期五": "fri",
    "周六": "sat",
    "星期六": "sat",
    "周日": "sun",
    "周天": "sun",
    "星期日": "sun",
    "星期天": "sun",
}

CN_DIGIT = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}

APPEND_KEYWORDS = ("还有", "再加", "另外", "额外", "再加上", "增加", "添加", "补上", "也多")
REPLACE_KEYWORDS = ("全部重来", "重新设置", "清空", "覆盖", "替换全部")


def parse_cn_hour_token(token: str) -> int | None:
    token = str(token or "").strip().replace("：", ":").replace("点半", ":30")
    if not token:
        return None
    if re.fullmatch(r"\d{1,2}", token):
        hour = int(token)
        return hour if 0 <= hour <= 23 else None
    if re.fullmatch(r"\d{1,2}:\d{1,2}", token):
        hour = int(token.split(":", 1)[0])
        return hour if 0 <= hour <= 23 else None
    match = re.fullmatch(r"([零一二两三四五六七八九十]+)(?:点|点钟|时)?(?::(\d{1,2}))?", token)
    if not match:
        return None
    cn = match.group(1)
    minute = int(match.group(2) or 0)
    if cn == "十":
        hour = 10
    elif len(cn) == 2 and cn[0] == "十":
        hour = 10 + CN_DIGIT.get(cn[1], 0)
    elif len(cn) == 2 and cn[1] == "十":
        hour = CN_DIGIT.get(cn[0], 0) * 10
    else:
        hour = CN_DIGIT.get(cn, 0)
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour
    return None


def format_hour_minute(hour: int, minute: int = 0) -> str:
    return f"{hour:02d}:{minute:02d}"


def mentioned_days_in_text(text: str) -> set[str]:
    days: set[str] = set()
    if re.search(r"工作日|周一到周五|周一至周五|星期一到星期五", text):
        days.update(["mon", "tue", "wed", "thu", "fri"])
    if re.search(r"周末|周六日|周六周日|星期六日|星期六和?星期天", text):
        days.update(["sat", "sun"])
    for label, key in DAY_NAME_TO_KEY.items():
        if len(label) <= 3 and label in text:
            days.add(key)
    return days


def extract_slots_from_user_message(message: str) -> list[dict[str, str]]:
    text = str(message or "").strip()
    if not text:
        return []
    days = mentioned_days_in_text(text) or set(WEEK_KEYS)
    slots: list[dict[str, str]] = []

    for match in re.finditer(
        r"(\d{1,2}:\d{2})\s*(?:到|至|-)\s*(\d{1,2}:\d{2})",
        text,
    ):
        start = match.group(1)
        end = match.group(2)
        for day in days:
            slots.append({"day": day, "start": start, "end": end})

    for match in re.finditer(
        r"([零一二两三四五六七八九十\d]{1,4})(?:点|点钟|时)(?::(\d{1,2})|分(\d{1,2})|半)?\s*(?:到|至|-)\s*([零一二两三四五六七八九十\d]{1,4})(?:点|点钟|时)(?::(\d{1,2})|分(\d{1,2})|半)?",
        text,
    ):
        left = match.group(1)
        right = match.group(4)
        left_minute = 30 if "半" in match.group(0).split("到")[0] else int(match.group(2) or match.group(3) or 0)
        right_minute = 30 if "半" in match.group(0).split("到")[-1] else int(match.group(5) or match.group(6) or 0)
        start_hour = parse_cn_hour_token(left)
        end_hour = parse_cn_hour_token(right)
        if start_hour is None or end_hour is None:
            continue
        start = format_hour_minute(start_hour, left_minute)
        end = format_hour_minute(end_hour, right_minute)
        for day in days:
            slots.append({"day": day, "start": start, "end": end})

    return slots


def detect_merge_mode(message: str, parsed: dict[str, Any], current: dict[str, list[dict[str, str]]]) -> str:
    mode = str(parsed.get("merge_mode", "")).strip()
    if mode in {"append", "replace_all", "replace_mentioned_days"}:
        return mode
    text = str(message or "")
    if any(keyword in text for keyword in REPLACE_KEYWORDS):
        return "replace_all"
    if any(keyword in text for keyword in APPEND_KEYWORDS):
        return "append"
    has_existing = any(current.get(key) for key in WEEK_KEYS)
    if has_existing and mentioned_days_in_text(text):
        return "append"
    return "replace_all"


def clone_availability(current: dict[str, list[dict[str, str]]]) -> dict[str, list[dict[str, str]]]:
    return {key: [dict(slot) for slot in current.get(key, [])] for key in WEEK_KEYS}


def append_slot(
    target: dict[str, list[dict[str, str]]],
    day: str,
    start: str,
    end: str,
) -> None:
    if day not in WEEK_KEYS or not start or not end:
        return
    candidate = {"start": start, "end": end}
    if candidate not in target[day]:
        target[day].append(candidate)


def collect_changes_from_parsed(parsed: dict[str, Any], merge_mode: str = "replace_all") -> list[dict[str, str]]:
    changes: list[dict[str, str]] = []
    raw_changes = parsed.get("changes")
    if isinstance(raw_changes, list):
        for item in raw_changes:
            if not isinstance(item, dict):
                continue
            day = str(item.get("day", "")).strip()
            if day in DAY_NAME_TO_KEY:
                day = DAY_NAME_TO_KEY[day]
            start = str(item.get("start", "")).strip()
            end = str(item.get("end", "")).strip()
            if day in WEEK_KEYS and start and end:
                changes.append({"day": day, "start": start, "end": end})
    if merge_mode == "append":
        return changes
    raw = parsed.get("weekly_availability")
    if raw is None:
        raw = parsed.get("weeklyAvailability")
    if isinstance(raw, dict):
        for day, slots in raw.items():
            key = DAY_NAME_TO_KEY.get(str(day), str(day))
            if key not in WEEK_KEYS or not isinstance(slots, list):
                continue
            for slot in slots:
                if not isinstance(slot, dict):
                    continue
                start = str(slot.get("start", "")).strip()
                end = str(slot.get("end", "")).strip()
                if start and end:
                    changes.append({"day": key, "start": start, "end": end})
    return changes


def apply_availability_changes(
    current: dict[str, list[dict[str, str]]],
    parsed: dict[str, Any],
    user_message: str,
) -> dict[str, list[dict[str, str]]]:
    merge_mode = detect_merge_mode(user_message, parsed, current)
    changes = collect_changes_from_parsed(parsed, merge_mode)

    if merge_mode == "append":
        result = clone_availability(current)
        if not changes:
            changes = extract_slots_from_user_message(user_message)
        else:
            for item in extract_slots_from_user_message(user_message):
                if item not in changes:
                    changes.append(item)
        for item in changes:
            append_slot(result, item["day"], item["start"], item["end"])
        return normalize_and_validate_availability(result)

    if merge_mode == "replace_mentioned_days":
        result = clone_availability(current)
        mentioned = mentioned_days_in_text(user_message)
        if not changes:
            changes = extract_slots_from_user_message(user_message)
        for day in mentioned:
            result[day] = []
        for item in changes:
            day = item["day"]
            if mentioned and day not in mentioned:
                continue
            append_slot(result, day, item["start"], item["end"])
        return normalize_and_validate_availability(result)

    payload = {key: [] for key in WEEK_KEYS}
    for item in changes:
        append_slot(payload, item["day"], item["start"], item["end"])
    if not any(payload.values()):
        raw = parsed.get("weekly_availability") or parsed.get("weeklyAvailability") or {}
        if isinstance(raw, dict):
            for key in WEEK_KEYS:
                slots = raw.get(key, [])
                if isinstance(slots, list):
                    payload[key] = [dict(slot) for slot in slots if isinstance(slot, dict)]
    return normalize_and_validate_availability(payload)


AVAILABILITY_PARSE_SYSTEM_PROMPT = """你是学习规划助手的「空闲时间段解析器」。用户会用自然语言描述每周什么时候有空学习。

请输出 JSON，格式如下：
{
  "reply": "用中文简短确认你理解到的变更",
  "merge_mode": "append",
  "changes": [
    {"day": "mon", "start": "07:00", "end": "08:00"}
  ]
}

merge_mode 取值：
- append：用户在已有安排上新增时段（如“还有”“再加”“另外”）
- replace_mentioned_days：只修改提到的日期（如“把周一改成...”）
- replace_all：首次设置或用户要求全部重来

规则：
- day 必须是 mon,tue,wed,thu,fri,sat,sun
- mon=周一, tue=周二, wed=周三, thu=周四, fri=周五, sat=周六, sun=周日
- start/end 为 24 小时 HH:MM
- append 模式只返回新增时段，不要重复返回已有 unchanged 时段
- replace_all 模式请同时返回 weekly_availability，包含完整一周 7 天
- 只输出 JSON，不要 markdown"""


def parse_availability_llm_response(
    content: str,
    current: dict[str, list[dict[str, str]]],
    user_message: str,
) -> tuple[str, dict[str, list[dict[str, str]]] | None]:
    try:
        parsed = extract_json_object(content)
    except json.JSONDecodeError:
        fallback = extract_slots_from_user_message(user_message)
        if fallback and any(keyword in user_message for keyword in APPEND_KEYWORDS):
            try:
                result = clone_availability(current)
                for item in fallback:
                    append_slot(result, item["day"], item["start"], item["end"])
                normalized = normalize_and_validate_availability(result)
                return "已根据你的描述追加空闲时段。", normalized
            except ValueError:
                pass
        return "抱歉，我没有正确理解，请再描述一次你的空闲时间。", None
    if not isinstance(parsed, dict):
        return "抱歉，解析结果无效，请再试一次。", None
    reply = str(parsed.get("reply", "")).strip() or "已解析你的空闲时间段。"
    try:
        normalized = apply_availability_changes(current, parsed, user_message)
    except ValueError as exc:
        return f"{reply}\n\n但时段格式有误：{exc}，请调整描述后重试。", None
    return reply, normalized


def build_availability_chat_messages(
    history: list[dict[str, str]],
    current_availability: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    context_lines = []
    for key in WEEK_KEYS:
        slots = current_availability.get(key, [])
        if slots:
            slot_text = "、".join(f"{s['start']}-{s['end']}" for s in slots)
            context_lines.append(f"{WEEK_LABELS[key]}：{slot_text}")
        else:
            context_lines.append(f"{WEEK_LABELS[key]}：无")
    context = "当前已保存的空闲时间：\n" + "\n".join(context_lines)
    messages: list[dict[str, str]] = [{"role": "system", "content": AVAILABILITY_PARSE_SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": context})
    for item in history:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


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


def build_time_shortage_details(
    tasks: list[dict[str, Any]],
    estimated_minutes_by_id: dict[str, int],
    scheduled_blocks: list[dict[str, Any]],
    total_slot_minutes: int,
) -> dict[str, Any]:
    scheduled_by_task: dict[str, int] = {}
    for block in scheduled_blocks:
        task_id = block["taskId"]
        scheduled_by_task[task_id] = scheduled_by_task.get(task_id, 0) + (
            block["endMinute"] - block["startMinute"]
        )

    total_needed = sum(estimated_minutes_by_id.values())
    total_scheduled = sum(scheduled_by_task.values())
    affected_tasks: list[dict[str, Any]] = []
    for task in tasks:
        task_id = task["id"]
        needed = int(estimated_minutes_by_id.get(task_id, 0))
        scheduled = int(scheduled_by_task.get(task_id, 0))
        if scheduled < needed:
            affected_tasks.append(
                {
                    "taskId": task_id,
                    "title": task.get("title", ""),
                    "deadline": task.get("deadline", ""),
                    "estimatedMinutes": needed,
                    "scheduledMinutes": scheduled,
                    "shortageMinutes": needed - scheduled,
                }
            )

    shortage_minutes = max(0, total_needed - total_slot_minutes)
    has_shortage = bool(affected_tasks) or shortage_minutes > 0

    return {
        "hasShortage": has_shortage,
        "totalNeededMinutes": total_needed,
        "totalAvailableMinutes": total_slot_minutes,
        "totalScheduledMinutes": total_scheduled,
        "shortageMinutes": shortage_minutes,
        "affectedTasks": affected_tasks,
    }


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
            "knowledgeFile": str(KNOWLEDGE_FILE.name),
            "pTypeSlowMultiplier": P_TYPE_SLOW_MULTIPLIER,
            "estimatePercentile": ESTIMATE_PERCENTILE,
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


@app.route("/api/settings/availability/chat", methods=["POST"])
def parse_availability_chat():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"message": "请输入要描述的空闲时间"}), 400
    history = payload.get("history", [])
    if not isinstance(history, list):
        history = []
    chat_history: list[dict[str, str]] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            chat_history.append({"role": role, "content": content})

    ok, model_msg = ollama_model_ready()
    if not ok:
        return jsonify({"message": f"Ollama 不可用：{model_msg}"}), 503

    with store_lock:
        state = load_user_state(username)
        current_availability = state["weeklyAvailability"]

    chat_history.append({"role": "user", "content": message})
    ollama_messages = build_availability_chat_messages(chat_history[:-1], current_availability)
    ollama_messages.append({"role": "user", "content": message})

    try:
        llm_res = ollama_chat(
            {
                "model": OLLAMA_MODEL,
                "messages": ollama_messages,
                "stream": False,
                "format": "json",
            }
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return jsonify({"message": f"模型响应超时（{OLLAMA_TIMEOUT_SEC} 秒内未返回）"}), 504
        return jsonify({"message": msg}), 503

    content = llm_res.get("message", {}).get("content", "{}")
    reply, normalized = parse_availability_llm_response(content, current_availability, message)
    applied = False
    if normalized is not None:
        with store_lock:
            state = load_user_state(username)
            state["weeklyAvailability"] = normalized
            save_user_state(username, state)
        applied = True

    return jsonify(
        {
            "reply": reply,
            "applied": applied,
            "weeklyAvailability": normalized,
        }
    )


@app.route("/api/tasks", methods=["POST"])
def create_task():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        cleaned = validate_task_payload(payload)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400

    task = {
        "id": str(uuid4()),
        "status": "todo",
        **cleaned,
    }
    with store_lock:
        state = load_user_state(username)
        state["tasks"].append(task)
        save_user_state(username, state)
    return jsonify(task), 201


@app.route("/api/tasks/<task_id>", methods=["PUT"])
def update_task(task_id: str):
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    try:
        cleaned = validate_task_payload(payload, partial=True)
    except ValueError as exc:
        return jsonify({"message": str(exc)}), 400
    with store_lock:
        state = load_user_state(username)
        task = next((item for item in state["tasks"] if item.get("id") == task_id), None)
        if task is None:
            return jsonify({"message": "task not found"}), 404
        task.update(cleaned)
        save_user_state(username, state)
    return jsonify(task)


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id: str):
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    with store_lock:
        state = load_user_state(username)
        before = len(state["tasks"])
        state["tasks"] = [task for task in state["tasks"] if task.get("id") != task_id]
        if len(state["tasks"]) == before:
            return jsonify({"message": "task not found"}), 404
        save_user_state(username, state)
    return jsonify({"ok": True})


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
    knowledge_records = load_knowledge_records()
    knowledge_indexed = index_knowledge_by_type(knowledge_records)
    rag_examples_by_task: dict[str, list[dict[str, Any]]] = {}
    evidence_packages_by_task: dict[str, dict[str, Any]] = {}
    for task in tasks:
        package, examples = build_task_rag_context(task, rag_samples, knowledge_indexed)
        evidence_packages_by_task[task["id"]] = package
        rag_examples_by_task[task["id"]] = examples

    prompt_context = build_llm_prompt_payload(
        tasks, availability, planning_start, planning_end, rag_examples_by_task, evidence_packages_by_task,
    )
    llm_payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a study planning assistant for constrained scheduling.\n"
                    "Hard rules:\n"
                    "1) Return JSON only, no markdown and no extra text.\n"
                    "2) You must estimate each task duration using evidence_package.parametric_estimate as baseline; cite rag_examples sample_id values.\n"
                    "   Adjust only within +/-15% unless evidence_package.warnings justify more.\n"
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
        task_package = evidence_packages_by_task.get(task_id, {})
        if task_id in est_map and est_map[task_id]["evidence_ids"]:
            est_val = clamp_minutes(int(est_map[task_id]["estimated_minutes"]))
            reason = est_map[task_id]["reason"]
            evidence_ids = est_map[task_id]["evidence_ids"]
        else:
            est_val, fallback_reason = fallback_estimate(task, task_examples, task_package)
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

    time_shortage = build_time_shortage_details(
        tasks,
        estimated_minutes_by_id,
        scheduled_blocks,
        total_slot_minutes,
    )

    details = {
        "rationale": llm_notes or "计划按DDL优先，并允许任务拆分到多个日期，只在用户空闲时段中安排。",
        "risks": risks,
        "taskEstimates": estimate_details,
        "ragTopK": RAG_TOP_K,
        "ragExamples": rag_examples_flat,
        "planningWindow": {"start": planning_start, "end": planning_end},
        "timeShortage": time_shortage,
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
