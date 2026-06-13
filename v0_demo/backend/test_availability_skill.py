#!/usr/bin/env python3
"""Tests for availability skill (LLM JSON apply path + rule fallback on parse failure)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

V0_DEMO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(V0_DEMO_ROOT))

from skills.availability import (  # noqa: E402
    detect_has_time_info,
    parse_availability_llm_response,
)
from skills.availability.parser import apply_availability_changes  # noqa: E402

EMPTY = {k: [] for k in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]}


def test_detect_time_info() -> None:
    assert detect_has_time_info("工作日晚上7点到9点有空") is True
    assert detect_has_time_info("我想设置一下") is False


def test_no_time_info_from_llm() -> None:
    reply, result, has_time, _, _ = parse_availability_llm_response(
        '{"has_time_info": false, "reply": "请补充时间"}',
        EMPTY,
        "我想设置一下",
    )
    assert has_time is False
    assert result is None
    assert "时间" in reply


def test_busy_excluded_from_weekly() -> None:
    parsed = {
        "has_time_info": True,
        "merge_mode": "replace_all",
        "polarity_trace": [
            {"day": "mon", "start": "19:00", "end": "21:00", "polarity": "available"},
            {"day": "tue", "start": "19:00", "end": "21:00", "polarity": "available"},
            {"day": "wed", "start": "19:00", "end": "21:00", "polarity": "busy"},
            {"day": "thu", "start": "19:00", "end": "21:00", "polarity": "available"},
            {"day": "fri", "start": "19:00", "end": "21:00", "polarity": "available"},
        ],
        "weekly_availability": {
            "mon": [{"start": "19:00", "end": "21:00"}],
            "tue": [{"start": "19:00", "end": "21:00"}],
            "wed": [],
            "thu": [{"start": "19:00", "end": "21:00"}],
            "fri": [{"start": "19:00", "end": "21:00"}],
            "sat": [],
            "sun": [],
        },
    }
    msg = "周一到周五晚上7点到9点有空，但周三晚上要上课"
    result = apply_availability_changes(EMPTY, parsed, msg)
    assert result["wed"] == []
    assert result["mon"] == [{"start": "19:00", "end": "21:00"}]


def test_fallback_rule_parse_on_invalid_json() -> None:
    reply, result, has_time, mode, _ = parse_availability_llm_response(
        "not json",
        EMPTY,
        "工作日晚上7点到9点有空",
    )
    assert has_time is True
    assert result is not None
    assert result["mon"] == [{"start": "19:00", "end": "21:00"}]
    assert result["fri"] == [{"start": "19:00", "end": "21:00"}]
    assert mode == "replace_all"


def test_mon_noon_tue_negation_llm_json() -> None:
    current = {
        "mon": [{"start": "01:00", "end": "02:00"}, {"start": "19:00", "end": "21:00"}],
        "tue": [{"start": "01:00", "end": "02:00"}],
        "wed": [],
        "thu": [],
        "fri": [{"start": "18:00", "end": "19:00"}],
        "sat": [{"start": "14:00", "end": "17:00"}],
        "sun": [{"start": "14:00", "end": "17:00"}],
    }
    msg = "我每周一中午一点到两点是有空的，但周二不是"
    llm_json = json.dumps(
        {
            "has_time_info": True,
            "merge_mode": "replace_mentioned_days",
            "reply": "已理解：周一中午 13:00-14:00 有空，周二同时段没空",
            "polarity_trace": [
                {"day": "mon", "start": "13:00", "end": "14:00", "polarity": "available"},
                {"day": "tue", "start": "13:00", "end": "14:00", "polarity": "busy"},
            ],
            "changes": [
                {"day": "mon", "start": "13:00", "end": "14:00", "polarity": "available"},
            ],
        }
    )
    reply, result, has_time, _, trace = parse_availability_llm_response(llm_json, current, msg)
    assert has_time is True
    assert result is not None
    assert result["mon"] == [{"start": "13:00", "end": "14:00"}]
    assert result["tue"] == []
    assert result["fri"] == [{"start": "18:00", "end": "19:00"}]
    assert result["sat"] == [{"start": "14:00", "end": "17:00"}]
    assert any(t.get("polarity") == "busy" and t["day"] == "tue" for t in trace)
    assert "周一" in reply


def test_append_daily_except_thursday_llm_json() -> None:
    current = {
        "mon": [{"start": "13:00", "end": "14:00"}],
        "tue": [{"start": "13:00", "end": "14:00"}],
        "wed": [],
        "thu": [],
        "fri": [{"start": "18:00", "end": "19:00"}],
        "sat": [{"start": "14:00", "end": "17:00"}],
        "sun": [{"start": "14:00", "end": "17:00"}],
    }
    msg = "我每天还有晚上七点到八点是有空的，但除了周四"
    changes = [
        {"day": day, "start": "19:00", "end": "20:00", "polarity": "available"}
        for day in ["mon", "tue", "wed", "fri", "sat", "sun"]
    ]
    trace = changes + [{"day": "thu", "start": "19:00", "end": "20:00", "polarity": "busy"}]
    llm_json = json.dumps(
        {
            "has_time_info": True,
            "merge_mode": "append",
            "reply": "已理解：除周四外，每天 19:00-20:00 有空",
            "polarity_trace": trace,
            "changes": changes,
        }
    )
    _, result, has_time, mode, _ = parse_availability_llm_response(llm_json, current, msg)
    assert has_time is True
    assert mode == "append"
    assert result is not None
    assert {"start": "19:00", "end": "20:00"} in result["mon"]
    assert {"start": "13:00", "end": "14:00"} in result["mon"]
    assert {"start": "19:00", "end": "20:00"} in result["tue"]
    assert {"start": "19:00", "end": "20:00"} in result["wed"]
    assert {"start": "19:00", "end": "20:00"} not in result["thu"]
    assert {"start": "19:00", "end": "20:00"} in result["fri"]
    assert {"start": "18:00", "end": "19:00"} in result["fri"]


def test_append_uses_weekly_when_changes_only_first_day() -> None:
    current = {
        "mon": [{"start": "13:00", "end": "14:00"}],
        "tue": [{"start": "13:00", "end": "14:00"}],
        "wed": [],
        "thu": [],
        "fri": [{"start": "18:00", "end": "19:00"}],
        "sat": [{"start": "14:00", "end": "17:00"}],
        "sun": [{"start": "14:00", "end": "17:00"}],
    }
    msg = "我每天还有晚上七点到八点是有空的，但除了周四"
    llm_json = json.dumps(
        {
            "has_time_info": True,
            "merge_mode": "append",
            "reply": "已理解：除周四外，每天 19:00-20:00 有空",
            "polarity_trace": [
                {"day": "thu", "start": "19:00", "end": "20:00", "polarity": "busy"},
            ],
            "changes": [
                {"day": "mon", "start": "19:00", "end": "20:00", "polarity": "available"},
            ],
            "weekly_availability": {
                day: [{"start": "19:00", "end": "20:00"}]
                for day in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
            },
        }
    )
    _, result, has_time, mode, _ = parse_availability_llm_response(llm_json, current, msg)
    assert has_time is True
    assert mode == "append"
    assert result is not None
    for day in ["mon", "tue", "wed", "fri", "sat", "sun"]:
        assert {"start": "19:00", "end": "20:00"} in result[day]
    assert {"start": "19:00", "end": "20:00"} not in result["thu"]


def main() -> None:
    test_detect_time_info()
    test_no_time_info_from_llm()
    test_busy_excluded_from_weekly()
    test_fallback_rule_parse_on_invalid_json()
    test_mon_noon_tue_negation_llm_json()
    test_append_daily_except_thursday_llm_json()
    test_append_uses_weekly_when_changes_only_first_day()
    print("All availability skill tests passed.")


if __name__ == "__main__":
    main()
