from __future__ import annotations

import re
from typing import Any

from .constants import WEEK_KEYS, WEEK_LABELS


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


def empty_weekly_availability() -> dict[str, list[dict[str, str]]]:
    return {key: [] for key in WEEK_KEYS}
