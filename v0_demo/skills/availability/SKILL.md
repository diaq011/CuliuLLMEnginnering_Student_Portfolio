---
name: availability-parser
description: >-
  Parses natural-language weekly free-time descriptions for the J人模拟器 app.
  Detects time expressions, classifies available vs busy slots, outputs
  weeklyAvailability JSON (Mon–Sun). Uses local Ollama. Use when implementing
  or debugging availability chat, 空闲时段, or POST /api/settings/availability/chat.
---

# Availability Parser Skill

## When to use

- User describes free/busy time in natural language (Chinese)
- Implementing or fixing **AI 设置空闲时间** in `v0_demo`
- Debugging `POST /api/settings/availability/chat`

## Read first

Full specification: [availabilitySkillSpec.md](./availabilitySkillSpec.md)

Examples: [examples.json](./examples.json)

## Core rules

1. **Detect time** — If no time words, return `has_time_info: false`; do not change saved data.
2. **Polarity** — Each slot is `available` or `busy`. Only **available** goes into `weekly_availability`.
3. **Output format** — 7 keys: `mon`…`sun`; each value is `[{start, end}]` in `HH:MM`.
4. **Ollama** — Local only: `OLLAMA_HOST` (default `http://127.0.0.1:11434`), `OLLAMA_MODEL` (default `qwen3:0.6b`).

## Implementation location

- **Handler（项目入口）**：[`handler.py`](./handler.py) — `AvailabilitySkillHandler.handle()`
- API 路由：[`v0_demo/backend/app.py`](../../backend/app.py) → `POST /api/settings/availability/chat`
- 解析逻辑：[`parser.py`](./parser.py)、[`prompt.py`](./prompt.py)

## LLM JSON shape (required fields)

```json
{
  "has_time_info": true,
  "reply": "中文确认",
  "merge_mode": "append",
  "polarity_trace": [
    {"day": "mon", "start": "19:00", "end": "21:00", "polarity": "available"}
  ],
  "changes": [
    {"day": "mon", "start": "19:00", "end": "21:00", "polarity": "available"}
  ],
  "weekly_availability": { "mon": [], "tue": [], "wed": [], "thu": [], "fri": [], "sat": [], "sun": [] }
}
```

- `changes` with `polarity: "busy"` must **not** appear in `weekly_availability`.
- `replace_all` must return full `weekly_availability` (available slots only).

## merge_mode quick reference

| Mode | User says |
|------|-----------|
| `append` | 还有、再加、另外 |
| `replace_mentioned_days` | 把周一改成… |
| `replace_all` | 首次设置、全部重来 |

## Polarity keywords

| available | busy |
|-----------|------|
| 有空、能学、方便、空闲 | 没空、忙、上课、补习、有事、考试 |

## Fallback

If Ollama JSON fails, use rule-based `extract_slots_from_user_message` (available only).
