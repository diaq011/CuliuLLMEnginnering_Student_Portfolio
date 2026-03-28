import json
from datetime import datetime, timedelta
from typing import List

from core.schemas import AvailabilityInput, TaskInput, normalize_plan
from services.ollama_client import OllamaClient


class PlannerService:
    def __init__(self, client: OllamaClient, max_days: int = 14) -> None:
        self.client = client
        self.max_days = max(3, max_days)

    def generate_daily_plan(self, tasks: List[TaskInput], availability: List[AvailabilityInput]) -> dict:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=self.max_days - 1)).strftime("%Y-%m-%d")

        system_prompt = (
            "You are a strict task planning assistant. "
            "Schedule tasks only within user availability. "
            "Daily planned minutes must not exceed available minutes. "
            "Break tasks by deadline priority into executable steps. "
            "Prefer 30-90 minute chunks to avoid over-fragmentation. "
            "Output must be JSON only."
        )

        compact_tasks = [
            {
                "name": t.name[:40],
                "detail": (t.detail or "")[:120],
                "estimated_minutes": t.estimated_minutes,
                "deadline": t.deadline,
            }
            for t in tasks
        ]

        user_payload = {
            "today": today,
            "planning_window": {"start_date": today, "end_date": end_date, "max_days": self.max_days},
            "goals": [
                "Create a daily plan starting today, up to planning_window.max_days.",
                "Each item includes date, step, minutes, and scheduled_slot.",
                "Limit one day to about 3-6 items.",
                "If overloaded, explain risk and suggest what to defer.",
            ],
            "tasks": compact_tasks,
            "availability": [s.to_dict() for s in availability],
            "output_schema": {
                "summary": "string",
                "risk": "string",
                "daily_plan": [
                    {
                        "date": "YYYY-MM-DD",
                        "total_available_minutes": 0,
                        "planned_minutes": 0,
                        "items": [
                            {
                                "task_name": "string",
                                "step": "string",
                                "minutes": 0,
                                "scheduled_slot": "HH:MM-HH:MM",
                            }
                        ],
                    }
                ],
                "notes": ["string"],
            },
        }

        user_payload = json.loads(json.dumps(user_payload, ensure_ascii=False))

        try:
            raw = self.client.chat_json(system_prompt, user_payload)
            return normalize_plan(raw)
        except Exception as exc:
            return self.generate_fallback_plan(tasks, availability, str(exc))

    def generate_fallback_plan(
        self,
        tasks: List[TaskInput],
        availability: List[AvailabilityInput],
        fail_reason: str,
    ) -> dict:
        today = datetime.now().date()

        ordered_tasks = sorted(tasks, key=lambda t: t.deadline)
        remaining = []
        for task in ordered_tasks:
            minutes = task.estimated_minutes if task.estimated_minutes and task.estimated_minutes > 0 else 60
            remaining.append({"task": task, "remaining": int(minutes), "step_idx": 1})

        weekday_to_slots: dict[int, list[tuple[int, int]]] = {i: [] for i in range(7)}
        weekday_index = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }

        def to_minutes(hhmm: str) -> int:
            hour, minute = hhmm.split(":")
            return int(hour) * 60 + int(minute)

        def to_hhmm(total_minutes: int) -> str:
            h = total_minutes // 60
            m = total_minutes % 60
            return f"{h:02d}:{m:02d}"

        for slot in availability:
            idx = weekday_index.get(slot.weekday)
            if idx is None:
                continue
            start_m = to_minutes(slot.start)
            end_m = to_minutes(slot.end)
            if end_m > start_m:
                weekday_to_slots[idx].append((start_m, end_m))

        for idx in weekday_to_slots:
            weekday_to_slots[idx].sort()

        daily_plan = []
        for day_offset in range(self.max_days):
            d = today + timedelta(days=day_offset)
            slots = weekday_to_slots.get(d.weekday(), [])
            if not slots:
                continue

            day_items = []
            day_planned = 0
            day_available = sum(end - start for start, end in slots)

            for start, end in slots:
                cursor = start
                while cursor < end and len(day_items) < 6:
                    current_task = next((r for r in remaining if r["remaining"] > 0), None)
                    if current_task is None:
                        break

                    slot_left = end - cursor
                    if slot_left <= 0:
                        break

                    chunk = min(90, slot_left, current_task["remaining"])
                    if chunk < 20:
                        break

                    task_obj = current_task["task"]
                    task_focus = task_obj.detail or task_obj.name
                    day_items.append(
                        {
                            "task_name": task_obj.name,
                            "step": f"Step {current_task['step_idx']}: work on {task_focus}",
                            "minutes": int(chunk),
                            "scheduled_slot": f"{to_hhmm(cursor)}-{to_hhmm(cursor + chunk)}",
                        }
                    )

                    cursor += chunk
                    day_planned += int(chunk)
                    current_task["remaining"] -= int(chunk)
                    current_task["step_idx"] += 1

                if all(r["remaining"] <= 0 for r in remaining):
                    break

            daily_plan.append(
                {
                    "date": d.strftime("%Y-%m-%d"),
                    "total_available_minutes": int(day_available),
                    "planned_minutes": int(day_planned),
                    "items": day_items,
                }
            )

            if all(r["remaining"] <= 0 for r in remaining):
                break

        unfinished = [r for r in remaining if r["remaining"] > 0]
        risk = "Some tasks are not fully scheduled in available slots." if unfinished else ""

        return {
            "summary": "Generated by local fallback planner because Ollama is unavailable.",
            "risk": risk,
            "daily_plan": daily_plan,
            "notes": [
                "Auto fallback is enabled to keep the website running.",
                f"Ollama error: {fail_reason}",
                "Retry later or switch to a smaller Ollama model for stability.",
            ],
        }