from __future__ import annotations

import json
import math
import os
import re
import secrets
import hashlib
import sys
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory

from deepseek_client import (
    AVAILABILITY_DEEPSEEK_MODEL,
    DEEPSEEK_MODEL,
    DEEPSEEK_TIMEOUT_SEC,
    deepseek_chat,
    deepseek_model_ready,
    extract_deepseek_content,
)
from knowledge_rag import (
    build_evidence_package,
    clamp_task_minutes,
    evidence_to_rag_examples,
    fallback_estimate_from_package,
    index_knowledge_by_type,
)
from assistant_agent import run_agent_turn

V0_DEMO_ROOT = Path(__file__).resolve().parent.parent
if str(V0_DEMO_ROOT) not in sys.path:
    sys.path.insert(0, str(V0_DEMO_ROOT))

from skills.availability import AvailabilitySkillHandler, normalize_and_validate_availability  # noqa: E402

app = Flask(__name__)
store_lock = Lock()
FRONTEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data"
USERS_FILE = DATA_DIR / "users.json"
USER_DATA_DIR = DATA_DIR / "users"
KNOWLEDGE_FILE = DATA_DIR / "knowledge" / "task_knowledge_v2.jsonl"
KNOWLEDGE_FILE_LEGACY = DATA_DIR / "knowledge" / "task_duration_knowledge.jsonl"

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


def default_user_state() -> dict[str, Any]:
    return {
        "tasks": [],
        "todayPlan": None,
        "plansByDate": {},
        "checkins": [],
        "lastPlanner": "none",
        "weeklyAvailability": {key: [] for key in WEEK_KEYS},
    }


PHONE_RE = re.compile(r"^1[3-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def classify_identifier(identifier: str) -> str | None:
    """Return 'phone' or 'email' for a valid identifier, else None."""
    if PHONE_RE.match(identifier):
        return "phone"
    if EMAIL_RE.match(identifier):
        return "email"
    return None


def normalize_identifier(raw: str) -> str:
    identifier = str(raw or "").strip()
    # Emails are case-insensitive; phones are digits. Lowercasing is safe for both.
    return identifier.lower()


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
    ok, msg = deepseek_model_ready()
    return jsonify(
        {
            "ok": True,
            "time": iso_now(),
            "deepseekApiUrl": os.getenv("DEEPSEEK_API_URL", "https://api.deepseek.com/v1"),
            "deepseekModel": DEEPSEEK_MODEL,
            "deepseekApiReady": ok,
            "deepseekMessage": msg,
            "availabilityDeepseekModel": AVAILABILITY_DEEPSEEK_MODEL,
            "deepseekTimeoutSec": DEEPSEEK_TIMEOUT_SEC,
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
    identifier = normalize_identifier(payload.get("identifier") or payload.get("username") or "")
    password = str(payload.get("password") or "")
    id_type = classify_identifier(identifier)
    if not id_type:
        return jsonify({"message": "请输入有效的手机号或邮箱"}), 400
    if len(password) < 6:
        return jsonify({"message": "密码至少需要 6 位"}), 400

    with store_lock:
        if identifier in users_db:
            return jsonify({"message": "该手机号/邮箱已注册，请直接登录"}), 409
        salt = secrets.token_hex(8)
        users_db[identifier] = {
            "salt": salt,
            "password_hash": hash_password(password, salt),
            "created_at": iso_now(),
            "type": id_type,
        }
        save_users()
        save_user_state(identifier, default_user_state())
        token = secrets.token_urlsafe(32)
        sessions[token] = identifier
    return jsonify({"ok": True, "user": {"username": identifier, "type": id_type}, "token": token, "isNew": True})


@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    payload = request.get_json(silent=True) or {}
    identifier = normalize_identifier(payload.get("identifier") or payload.get("username") or "")
    password = str(payload.get("password") or "")
    with store_lock:
        user = users_db.get(identifier)
        if not user:
            return jsonify({"message": "手机号/邮箱或密码错误"}), 401
        expected = hash_password(password, user.get("salt", ""))
        if expected != user.get("password_hash"):
            return jsonify({"message": "手机号/邮箱或密码错误"}), 401
        token = secrets.token_urlsafe(32)
        sessions[token] = identifier
    return jsonify({"ok": True, "user": {"username": identifier, "type": user.get("type")}, "token": token})


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

    ok, model_msg = deepseek_model_ready()
    if not ok:
        return jsonify({"message": f"DeepSeek API 不可用：{model_msg}"}), 503

    with store_lock:
        state = load_user_state(username)
        current_availability = state["weeklyAvailability"]

    handler = AvailabilitySkillHandler(deepseek_chat, AVAILABILITY_DEEPSEEK_MODEL, is_deepseek=True)
    try:
        result = handler.handle(message, current_availability, chat_history)
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return jsonify({"message": f"模型响应超时（{DEEPSEEK_TIMEOUT_SEC} 秒内未返回）"}), 504
        return jsonify({"message": msg}), 503

    if result.applied and result.weekly_availability is not None:
        with store_lock:
            state = load_user_state(username)
            state["weeklyAvailability"] = result.weekly_availability
            save_user_state(username, state)

    return jsonify(result.to_api_dict())


@app.route("/api/chat", methods=["POST"])
def assistant_chat():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    if not message:
        return jsonify({"message": "请输入内容"}), 400
    history = payload.get("history", [])
    if not isinstance(history, list):
        history = []
    clean_history: list[dict[str, str]] = []
    for item in history[-12:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            clean_history.append({"role": role, "content": content})

    ok, model_msg = deepseek_model_ready()
    if not ok:
        return jsonify({"message": f"DeepSeek API 不可用：{model_msg}"}), 503

    def dispatch_tool(name: str, args: dict[str, Any]) -> tuple[Any, list[str]]:
        if name == "set_availability":
            description = str(args.get("description") or "").strip()
            if not description:
                return {"error": "缺少空闲时间描述"}, []
            with store_lock:
                state = load_user_state(username)
                current = state["weeklyAvailability"]
            handler = AvailabilitySkillHandler(deepseek_chat, AVAILABILITY_DEEPSEEK_MODEL, is_deepseek=True)
            result = handler.handle(description, current, [])
            if result.applied and result.weekly_availability is not None:
                with store_lock:
                    state = load_user_state(username)
                    state["weeklyAvailability"] = result.weekly_availability
                    save_user_state(username, state)
                return (
                    {"applied": True, "reply": result.reply, "weeklyAvailability": result.weekly_availability},
                    ["availability"],
                )
            return {"applied": False, "reply": result.reply, "has_time_info": result.has_time_info}, []

        if name == "add_task":
            try:
                cleaned = validate_task_payload(
                    {
                        "title": args.get("title"),
                        "deadline": args.get("deadline"),
                        "subject": args.get("subject") or "general",
                        "taskType": args.get("taskType") or "exercise_set",
                        "difficulty": args.get("difficulty") or "medium",
                        "estimatedMinutes": args.get("estimatedMinutes"),
                    }
                )
            except ValueError as exc:
                return {"error": str(exc)}, []
            task = {"id": str(uuid4()), "status": "todo", **cleaned}
            with store_lock:
                state = load_user_state(username)
                state["tasks"].append(task)
                save_user_state(username, state)
            return (
                {"ok": True, "task": {"id": task["id"], "title": task["title"], "deadline": task["deadline"]}},
                ["tasks"],
            )

        if name == "generate_plan":
            date = str(args.get("date") or today_str()).strip()
            try:
                gen = run_plan_generation(username, date)
            except PlanGenerationError as exc:
                return {"error": exc.message}, []
            plan = gen.get("plan", {})
            shortage = (plan.get("details", {}) or {}).get("timeShortage", {})
            return (
                {
                    "ok": True,
                    "date": plan.get("date"),
                    "planningWindow": gen.get("planningWindow"),
                    "totalEstimatedMinutes": plan.get("totalEstimatedMinutes"),
                    "taskCount": len(plan.get("taskIds", [])),
                    "hasShortage": bool(shortage.get("hasShortage")),
                },
                ["plan"],
            )

        if name == "list_tasks":
            with store_lock:
                state = load_user_state(username)
            tasks = [
                {
                    "title": t.get("title"),
                    "deadline": t.get("deadline"),
                    "subject": SUBJECT_LABELS.get(t.get("subject", "general"), "综合/其他"),
                    "status": t.get("status"),
                }
                for t in state["tasks"]
            ]
            return {"tasks": tasks, "count": len(tasks)}, []

        if name == "get_plan":
            date = str(args.get("date") or today_str()).strip()
            with store_lock:
                state = load_user_state(username)
                plan = state["plansByDate"].get(date)
            return {"date": date, "plan": plan}, []

        return {"error": f"unknown tool: {name}"}, []

    agent_context = {"today": today_str(), "weekday_key": current_week_key()}
    try:
        result = run_agent_turn(
            deepseek_chat,
            DEEPSEEK_MODEL,
            clean_history,
            message,
            dispatch_tool,
            context=agent_context,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return jsonify({"message": f"模型响应超时（{DEEPSEEK_TIMEOUT_SEC} 秒内未返回）"}), 504
        return jsonify({"message": f"模型调用失败：{msg}"}), 502

    return jsonify(result)


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


class PlanGenerationError(Exception):
    """Raised by run_plan_generation; carries an HTTP-friendly message and status."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def run_plan_generation(username: str, target_date: str) -> dict[str, Any]:
    """Core plan-generation logic, reusable by the HTTP route and the chat agent.

    Returns {"plan", "planner", "planningWindow"} on success.
    Raises PlanGenerationError(message, status) on any recoverable failure.
    """
    target_date = str(target_date or today_str()).strip()
    try:
        planning_start_dt = parse_date(target_date)
    except ValueError:
        raise PlanGenerationError("date must be YYYY-MM-DD", 400)

    with store_lock:
        state = load_user_state(username)
        tasks = [task for task in state["tasks"] if task["status"] != "done"]
        availability = state["weeklyAvailability"]

    if not tasks:
        raise PlanGenerationError("请先添加至少一个任务，再生成计划", 400)

    max_deadline_dt = max(parse_date(task["deadline"]) for task in tasks)
    planning_end_dt = max(planning_start_dt, max_deadline_dt)
    planning_start = format_date(planning_start_dt)
    planning_end = format_date(planning_end_dt)

    segments_by_date = build_day_segments(availability, planning_start_dt, planning_end_dt)
    total_slot_minutes = sum(max(0, e - s) for segs in segments_by_date.values() for s, e in segs)
    if total_slot_minutes <= 0:
        raise PlanGenerationError("从今天到任务DDL前都没有可用空闲时段，请先在设置中配置", 400)

    ok, model_msg = deepseek_model_ready()
    if not ok:
        raise PlanGenerationError(f"DeepSeek API 不可用：{model_msg}", 503)

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
        "model": DEEPSEEK_MODEL,
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
        llm_res = deepseek_chat(llm_payload)
        content = extract_deepseek_content(llm_res)
        parsed = json.loads(content)
        order, est_map, llm_risks, llm_notes = parse_llm_plan(tasks, parsed, rag_examples_by_task)
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            raise PlanGenerationError(f"模型响应超时（{DEEPSEEK_TIMEOUT_SEC} 秒内未返回）", 504)
        raise PlanGenerationError(f"模型调用失败：{msg}", 502)
    except PlanGenerationError:
        raise
    except Exception as exc:
        raise PlanGenerationError(f"模型解析失败：{exc}", 502)

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
        state["lastPlanner"] = f"deepseek:{DEEPSEEK_MODEL}+rag_top_k={RAG_TOP_K}"
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
    return {
        "plan": plan,
        "planner": state["lastPlanner"],
        "planningWindow": {"start": planning_start, "end": planning_end},
    }


@app.route("/api/plans/generate", methods=["POST"])
def generate_plan_for_date():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    req_payload = request.get_json(silent=True) or {}
    target_date = str(req_payload.get("date") or today_str()).strip()
    try:
        result = run_plan_generation(username, target_date)
    except PlanGenerationError as exc:
        return jsonify({"message": exc.message}), exc.status
    return jsonify(result)


@app.route("/api/plans/today", methods=["POST"])
def build_today_plan():
    username = get_current_username()
    if not username:
        return jsonify({"message": "unauthorized"}), 401
    try:
        result = run_plan_generation(username, today_str())
    except PlanGenerationError as exc:
        return jsonify({"message": exc.message}), exc.status
    return jsonify(result)


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
