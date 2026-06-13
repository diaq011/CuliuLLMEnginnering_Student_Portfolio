from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from .constants import (
    APPEND_KEYWORDS,
    AVAILABLE_KEYWORDS,
    BUSY_KEYWORDS,
    CN_DIGIT,
    CONTRAST_SPLITTERS,
    DAY_NAME_TO_KEY,
    NEGATION_MARKERS,
    PERIOD_KEYWORDS,
    REPLACE_KEYWORDS,
    TIME_INFO_PATTERNS,
    WEEK_KEYS,
    WEEK_LABELS,
)
from .utils import extract_json_object
from .validation import normalize_and_validate_availability


@dataclass
class StructuredAvailability:
    available: list[dict[str, str]] = field(default_factory=list)
    busy: list[dict[str, str]] = field(default_factory=list)
    polarity_trace: list[dict[str, str]] = field(default_factory=list)
    merge_mode: str = "replace_mentioned_days"
    time_range: tuple[str, str] | None = None


def detect_has_time_info(message: str) -> bool:
    text = str(message or "").strip()
    if not text:
        return False
    return any(re.search(pattern, text) for pattern in TIME_INFO_PATTERNS)


def detect_period(text: str) -> str | None:
    for period, keywords in PERIOD_KEYWORDS:
        if any(kw in text for kw in keywords):
            return period
    return None


def adjust_hour_for_period(hour: int, period: str | None) -> int:
    if period == "noon":
        if 1 <= hour <= 10:
            return hour + 12
        return hour
    if period == "afternoon":
        if 1 <= hour <= 11:
            return hour + 12
        return hour
    if period == "evening":
        if 1 <= hour <= 11:
            return hour + 12
        return hour
    if period == "morning":
        return hour
    if period == "late_night":
        if hour == 12:
            return 0
        return hour
    return hour


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


def split_contrast_clauses(text: str) -> tuple[str, str | None]:
    for sep in CONTRAST_SPLITTERS:
        if sep in text:
            left, right = text.split(sep, 1)
            return left.strip(), right.strip()
    return text.strip(), None


def is_negation_clause(clause: str) -> bool:
    clause = str(clause or "").strip()
    if not clause:
        return False
    has_neg = any(m in clause for m in NEGATION_MARKERS) or any(kw in clause for kw in BUSY_KEYWORDS)
    has_pos = any(kw in clause for kw in AVAILABLE_KEYWORDS)
    if has_neg and not has_pos:
        return True
    if has_neg and re.search(r"不是(有空)?$|不是$", clause):
        return True
    return False


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


def extract_time_range_from_clause(clause: str) -> tuple[str, str] | None:
    text = str(clause or "").strip()
    if not text:
        return None
    period = detect_period(text)

    match = re.search(
        r"(\d{1,2}:\d{2})\s*(?:到|至|-)\s*(\d{1,2}:\d{2})",
        text,
    )
    if match:
        return match.group(1), match.group(2)

    match = re.search(
        r"([零一二两三四五六七八九十\d]{1,4})(?:点|点钟|时)?(?::(\d{1,2})|分(\d{1,2})|半)?\s*(?:到|至|-)\s*([零一二两三四五六七八九十\d]{1,4})(?:点|点钟|时)?(?::(\d{1,2})|分(\d{1,2})|半)?",
        text,
    )
    if not match:
        return None
    left = match.group(1)
    right = match.group(4)
    left_minute = 30 if "半" in match.group(0).split("到")[0] else int(match.group(2) or match.group(3) or 0)
    right_minute = 30 if "半" in match.group(0).split("到")[-1] else int(match.group(5) or match.group(6) or 0)
    start_hour = parse_cn_hour_token(left)
    end_hour = parse_cn_hour_token(right)
    if start_hour is None or end_hour is None:
        return None
    start_hour = adjust_hour_for_period(start_hour, period)
    end_hour = adjust_hour_for_period(end_hour, period)
    return format_hour_minute(start_hour, left_minute), format_hour_minute(end_hour, right_minute)


def extract_structured_from_message(message: str) -> StructuredAvailability | None:
    text = str(message or "").strip()
    if not text:
        return None
    positive, negative = split_contrast_clauses(text)
    time_range = extract_time_range_from_clause(positive) or extract_time_range_from_clause(text)
    if not time_range:
        return None

    start, end = time_range
    available_days = mentioned_days_in_text(positive) if positive else mentioned_days_in_text(text)
    if not available_days and not negative:
        available_days = mentioned_days_in_text(text) or set(WEEK_KEYS)

    busy_days: set[str] = set()
    if negative and is_negation_clause(negative):
        busy_days = mentioned_days_in_text(negative)

    if negative and not busy_days:
        busy_days = mentioned_days_in_text(negative) - available_days

    structured = StructuredAvailability(time_range=time_range)
    for day in sorted(available_days):
        if day in busy_days:
            continue
        structured.available.append({"day": day, "start": start, "end": end})
        structured.polarity_trace.append(
            {"day": day, "start": start, "end": end, "polarity": "available"}
        )
    for day in sorted(busy_days):
        structured.busy.append({"day": day, "start": start, "end": end})
        structured.polarity_trace.append(
            {"day": day, "start": start, "end": end, "polarity": "busy"}
        )

    if any(kw in text for kw in APPEND_KEYWORDS):
        structured.merge_mode = "append"
    elif any(kw in text for kw in REPLACE_KEYWORDS):
        structured.merge_mode = "replace_all"
    elif negative or (available_days and len(available_days) <= 3):
        structured.merge_mode = "replace_mentioned_days"
    else:
        structured.merge_mode = "replace_all"

    if not structured.available and not structured.busy:
        return None
    return structured


def extract_slots_from_user_message(message: str) -> list[dict[str, str]]:
    structured = extract_structured_from_message(message)
    if structured:
        return [dict(item) for item in structured.available]
    text = str(message or "").strip()
    if not text:
        return []
    days = mentioned_days_in_text(text) or set(WEEK_KEYS)
    period = detect_period(text)
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
        start_hour = adjust_hour_for_period(start_hour, period)
        end_hour = adjust_hour_for_period(end_hour, period)
        start = format_hour_minute(start_hour, left_minute)
        end = format_hour_minute(end_hour, right_minute)
        for day in days:
            slots.append({"day": day, "start": start, "end": end})

    return slots


def remove_slot_exact(
    target: dict[str, list[dict[str, str]]],
    day: str,
    start: str,
    end: str,
) -> None:
    if day not in target:
        return
    target[day] = [
        slot
        for slot in target[day]
        if not (slot.get("start") == start and slot.get("end") == end)
    ]


def remove_erroneous_am_pair(
    target: dict[str, list[dict[str, str]]],
    day: str,
    pm_start: str,
    pm_end: str,
) -> None:
    """Drop 01:00-02:00 when user meant 13:00-14:00 (中午)."""
    try:
        sh, sm = pm_start.split(":")
        eh, em = pm_end.split(":")
        if int(sh) >= 12 and int(eh) >= 12:
            am_start = f"{int(sh) - 12:02d}:{sm}"
            am_end = f"{int(eh) - 12:02d}:{em}"
            remove_slot_exact(target, day, am_start, am_end)
    except Exception:
        pass


def apply_structured_availability(
    current: dict[str, list[dict[str, str]]],
    structured: StructuredAvailability,
) -> dict[str, list[dict[str, str]]]:
    merge_mode = structured.merge_mode
    if merge_mode == "replace_all":
        result = {key: [] for key in WEEK_KEYS}
    else:
        result = clone_availability(current)

    touched_days = {item["day"] for item in structured.available} | {item["day"] for item in structured.busy}
    if merge_mode == "replace_mentioned_days":
        for day in touched_days:
            result[day] = []

    for item in structured.busy:
        remove_slot_exact(result, item["day"], item["start"], item["end"])
        remove_erroneous_am_pair(result, item["day"], item["start"], item["end"])

    for item in structured.available:
        day, start, end = item["day"], item["start"], item["end"]
        remove_erroneous_am_pair(result, day, start, end)
        append_slot(result, day, start, end)

    return normalize_and_validate_availability(result)


def try_rule_based_availability(
    message: str,
    current: dict[str, list[dict[str, str]]],
) -> tuple[str, dict[str, list[dict[str, str]]] | None, str, list[dict[str, str]]] | None:
    structured = extract_structured_from_message(message)
    if not structured or not structured.time_range:
        return None
    start, end = structured.time_range
    avail_days = [WEEK_LABELS.get(d["day"], d["day"]) for d in structured.available]
    busy_days = [WEEK_LABELS.get(d["day"], d["day"]) for d in structured.busy]
    parts = []
    if avail_days:
        parts.append(f"{'、'.join(avail_days)} {start}-{end} 有空")
    if busy_days:
        parts.append(f"{'、'.join(busy_days)} 同时段没空，未写入")
    reply = "已理解：" + ("；".join(parts) if parts else f"时段 {start}-{end}")
    try:
        normalized = apply_structured_availability(current, structured)
    except ValueError as exc:
        return f"时段格式有误：{exc}", None, structured.merge_mode, structured.polarity_trace
    return reply, normalized, structured.merge_mode, structured.polarity_trace


def extract_polarity_trace(parsed: dict[str, Any]) -> list[dict[str, str]]:
    trace: list[dict[str, str]] = []
    raw = parsed.get("polarity_trace")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            day = str(item.get("day", "")).strip()
            if day in DAY_NAME_TO_KEY:
                day = DAY_NAME_TO_KEY[day]
            start = str(item.get("start", "")).strip()
            end = str(item.get("end", "")).strip()
            polarity = str(item.get("polarity", "available")).strip().lower()
            if day in WEEK_KEYS and start and end:
                trace.append({"day": day, "start": start, "end": end, "polarity": polarity})
    if trace:
        return trace
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
            polarity = str(item.get("polarity", "available")).strip().lower()
            if day in WEEK_KEYS and start and end:
                trace.append({"day": day, "start": start, "end": end, "polarity": polarity})
    return trace


def filter_available_changes(changes: list[dict[str, str]], parsed: dict[str, Any]) -> list[dict[str, str]]:
    trace = extract_polarity_trace(parsed)
    busy_keys = {
        (t["day"], t["start"], t["end"])
        for t in trace
        if t.get("polarity") == "busy"
    }
    result: list[dict[str, str]] = []
    for item in changes:
        key = (item["day"], item["start"], item["end"])
        if key in busy_keys:
            continue
        polarity = item.get("polarity", "available")
        if str(polarity).lower() == "busy":
            continue
        result.append({"day": item["day"], "start": item["start"], "end": item["end"]})
    return result


def detect_merge_mode(message: str, parsed: dict[str, Any], current: dict[str, list[dict[str, str]]]) -> str:
    text = str(message or "")
    llm_mode = str(parsed.get("merge_mode", "")).strip()

    if any(keyword in text for keyword in REPLACE_KEYWORDS):
        return "replace_all"
    if any(keyword in text for keyword in APPEND_KEYWORDS):
        return "append"
    if any(sep in text for sep in CONTRAST_SPLITTERS):
        return "replace_mentioned_days"
    if llm_mode in {"append", "replace_all", "replace_mentioned_days"}:
        return llm_mode
    has_existing = any(current.get(key) for key in WEEK_KEYS)
    if has_existing and mentioned_days_in_text(text):
        return "replace_mentioned_days"
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
    existing_keys: set[tuple[str, str, str]] = set()
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
            polarity = str(item.get("polarity", "available")).strip().lower()
            if day in WEEK_KEYS and start and end:
                key = (day, start, end)
                if key not in existing_keys:
                    changes.append({"day": day, "start": start, "end": end, "polarity": polarity})
                    existing_keys.add(key)
    changes = filter_available_changes(changes, parsed)

    trace = extract_polarity_trace(parsed)
    existing_keys = {(c["day"], c["start"], c["end"]) for c in changes}
    for item in trace:
        if str(item.get("polarity", "available")).lower() == "busy":
            continue
        key = (item["day"], item["start"], item["end"])
        if key not in existing_keys:
            changes.append({"day": item["day"], "start": item["start"], "end": item["end"]})
            existing_keys.add(key)
    changes = filter_available_changes(changes, parsed)

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
                    candidate_key = (key, start, end)
                    if candidate_key not in existing_keys:
                        changes.append({"day": key, "start": start, "end": end})
                        existing_keys.add(candidate_key)
    return filter_available_changes(changes, parsed)


def apply_busy_exclusions(
    result: dict[str, list[dict[str, str]]],
    parsed: dict[str, Any],
    user_message: str,
) -> dict[str, list[dict[str, str]]]:
    trace = extract_polarity_trace(parsed)
    for item in trace:
        if str(item.get("polarity", "available")).lower() != "busy":
            continue
        remove_slot_exact(result, item["day"], item["start"], item["end"])
        remove_erroneous_am_pair(result, item["day"], item["start"], item["end"])
    return result


def apply_availability_changes(
    current: dict[str, list[dict[str, str]]],
    parsed: dict[str, Any],
    user_message: str,
) -> dict[str, list[dict[str, str]]]:
    merge_mode = detect_merge_mode(user_message, parsed, current)
    changes = collect_changes_from_parsed(parsed, merge_mode)

    if merge_mode == "append":
        result = clone_availability(current)
        for item in changes:
            append_slot(result, item["day"], item["start"], item["end"])
            remove_erroneous_am_pair(result, item["day"], item["start"], item["end"])
        result = apply_busy_exclusions(result, parsed, user_message)
        return normalize_and_validate_availability(result)

    if merge_mode == "replace_mentioned_days":
        result = clone_availability(current)
        mentioned = mentioned_days_in_text(user_message)
        trace = extract_polarity_trace(parsed)
        busy_days = {t["day"] for t in trace if str(t.get("polarity", "")).lower() == "busy"}
        mentioned |= busy_days
        for day in mentioned:
            result[day] = []
        for item in changes:
            day = item["day"]
            if mentioned and day not in mentioned:
                continue
            append_slot(result, day, item["start"], item["end"])
            remove_erroneous_am_pair(result, day, item["start"], item["end"])
        result = apply_busy_exclusions(result, parsed, user_message)
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
    payload = apply_busy_exclusions(payload, parsed, user_message)
    return normalize_and_validate_availability(payload)


def parse_availability_llm_response(
    content: str,
    current: dict[str, list[dict[str, str]]],
    user_message: str,
) -> tuple[str, dict[str, list[dict[str, str]]] | None, bool, str, list[dict[str, str]]]:
    merge_mode = "replace_all"
    polarity_trace: list[dict[str, str]] = []

    try:
        parsed = extract_json_object(content)
    except json.JSONDecodeError:
        has_time = detect_has_time_info(user_message)
        if not has_time:
            return "请具体描述你的空闲时间，例如：工作日晚上 7 点到 9 点有空。", None, False, merge_mode, []
        fallback = extract_slots_from_user_message(user_message)
        structured = extract_structured_from_message(user_message)
        if structured:
            try:
                normalized = apply_structured_availability(current, structured)
                reply = try_rule_based_availability(user_message, current)[0]
                return reply, normalized, True, structured.merge_mode, structured.polarity_trace
            except ValueError:
                pass
        if fallback and any(keyword in user_message for keyword in APPEND_KEYWORDS):
            try:
                result = clone_availability(current)
                for item in fallback:
                    append_slot(result, item["day"], item["start"], item["end"])
                normalized = normalize_and_validate_availability(result)
                return "已根据你的描述追加空闲时段。", normalized, True, "append", []
            except ValueError:
                pass
        if fallback:
            try:
                payload = {key: [] for key in WEEK_KEYS}
                for item in fallback:
                    append_slot(payload, item["day"], item["start"], item["end"])
                normalized = normalize_and_validate_availability(payload)
                return "已根据你的描述解析空闲时段。", normalized, True, "replace_all", []
            except ValueError:
                pass
        return "抱歉，我没有正确理解，请再描述一次你的空闲时间。", None, False, merge_mode, []

    if not isinstance(parsed, dict):
        return "抱歉，解析结果无效，请再试一次。", None, False, merge_mode, []

    has_time = bool(parsed.get("has_time_info", False))
    if not has_time:
        reply = str(parsed.get("reply", "")).strip() or "请具体描述你的空闲时间，例如：工作日晚上 7 点到 9 点有空。"
        return reply, None, False, merge_mode, []

    merge_mode = detect_merge_mode(user_message, parsed, current)
    polarity_trace = extract_polarity_trace(parsed)
    reply = str(parsed.get("reply", "")).strip() or "已解析你的空闲时间段。"
    try:
        normalized = apply_availability_changes(current, parsed, user_message)
    except ValueError as exc:
        return f"{reply}\n\n但时段格式有误：{exc}，请调整描述后重试。", None, True, merge_mode, polarity_trace
    return reply, normalized, True, merge_mode, polarity_trace
