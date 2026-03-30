import json
import time
from datetime import datetime, timedelta
from typing import List

from core.schemas import AvailabilityInput, TaskInput, normalize_plan
from services.ollama_client import OllamaClient


class PlannerService:
    def __init__(
        self,
        client: OllamaClient,
        max_days: int = 14,
        quality_model: str | None = None,
        fast_timeout_seconds: int = 12,
    ) -> None:
        self.client = client
        self.max_days = max(3, max_days)
        self.quality_model = quality_model
        self.fast_timeout_seconds = max(4, fast_timeout_seconds)
        self.prefer_quality = False

    def set_prefer_quality(self, prefer_quality: bool) -> None:
        self.prefer_quality = prefer_quality

    def generate_daily_plan(self, tasks: List[TaskInput], availability: List[AvailabilityInput]) -> dict:
        started = time.perf_counter()
        base_plan = self._build_rule_based_plan(tasks, availability)

        use_model = self.quality_model if (self.prefer_quality and self.quality_model) else self.client.model
        system_prompt = (
            "你是任务规划助手。你必须严格只输出一个 JSON 对象，不允许输出 Markdown、解释文本、代码块。"
            "你必须遵守以下规则："
            "1) 计划任务只能出现在用户提供的空闲时段内；"
            "2) 在满足截止日期(DDL)前提下尽量均衡每天任务量，不要出现某天极端堆积；"
            "3) 优先安排更临近 DDL 的任务，尽量降低逾期风险；"
            "4) 若输入信息不足以给出高置信度计划，允许你发起补充提问。"
            "输出字段必须包含：summary, risk, need_more_info, questions, daily_plan, notes。"
            "当 need_more_info=true 时，questions 至少包含 1 个明确问题。"
        )

        user_payload = {
            "objective": "Refine wording and step clarity while preserving feasible schedule.",
            "constraints": {
                "max_days": self.max_days,
                "minutes_must_fit_availability": True,
                "chunk_minutes_prefer": "30-90",
                "keep_output_compact": True,
                "avoid_missing_deadline": True,
                "balance_daily_load": True,
            },
            "tasks": [
                {
                    "name": t.name[:40],
                    "detail": (t.detail or "")[:120],
                    "estimated_minutes": t.estimated_minutes,
                    "deadline": t.deadline,
                }
                for t in tasks
            ],
            "draft_plan": {
                "summary": base_plan.get("summary", ""),
                "risk": base_plan.get("risk", ""),
                "daily_plan": base_plan.get("daily_plan", []),
            },
            "output_schema": {
                "summary": "string",
                "risk": "string",
                "need_more_info": "boolean",
                "questions": ["string"],
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
            raw = self.client.chat_json(
                system_prompt=system_prompt,
                user_payload=user_payload,
                timeout_seconds=self.fast_timeout_seconds,
                model=use_model,
            )
            refined = normalize_plan(raw)
            final_plan = self._merge_with_base(base_plan, refined)
            metrics = self.client.get_last_metrics()
            final_plan["meta"] = {
                "mode": "llm_refined",
                "used_fallback": False,
                "model": metrics.get("model", use_model),
                "llm_elapsed_ms": metrics.get("elapsed_ms"),
                "elapsed_ms_total": int((time.perf_counter() - started) * 1000),
                "error": None,
            }
            return final_plan
        except Exception as exc:
            notes = list(base_plan.get("notes", []))
            notes.append("本次已切换为本地快速排程，确保你可以先执行再微调。")
            notes.append(f"LLM 未在快速窗口内完成：{str(exc)}")
            base_plan["notes"] = notes
            metrics = self.client.get_last_metrics()
            base_plan["meta"] = {
                "mode": "local_fallback",
                "used_fallback": True,
                "model": metrics.get("model", use_model),
                "llm_elapsed_ms": metrics.get("elapsed_ms"),
                "elapsed_ms_total": int((time.perf_counter() - started) * 1000),
                "error": str(exc),
            }
            return base_plan

    def _build_rule_based_plan(self, tasks: List[TaskInput], availability: List[AvailabilityInput]) -> dict:
        today = datetime.now().date()

        def parse_date(text: str):
            try:
                return datetime.strptime(text, "%Y-%m-%d").date()
            except Exception:
                return today + timedelta(days=self.max_days - 1)

        def to_minutes(hhmm: str) -> int:
            hour, minute = hhmm.split(":")
            return int(hour) * 60 + int(minute)

        def to_hhmm(total_minutes: int) -> str:
            h = total_minutes // 60
            m = total_minutes % 60
            return f"{h:02d}:{m:02d}"

        ordered_tasks = sorted(tasks, key=lambda t: parse_date(t.deadline))
        remaining = [
            {
                "task": task,
                "remaining": int(task.estimated_minutes) if task.estimated_minutes and task.estimated_minutes > 0 else 60,
                "step_idx": 1,
                "deadline": parse_date(task.deadline),
            }
            for task in ordered_tasks
        ]

        weekday_index = {
            "Monday": 0,
            "Tuesday": 1,
            "Wednesday": 2,
            "Thursday": 3,
            "Friday": 4,
            "Saturday": 5,
            "Sunday": 6,
        }

        slots_by_weekday = {i: [] for i in range(7)}
        for slot in availability:
            idx = weekday_index.get(slot.weekday)
            if idx is None:
                continue
            start_m = to_minutes(slot.start)
            end_m = to_minutes(slot.end)
            if end_m > start_m:
                slots_by_weekday[idx].append((start_m, end_m))

        for idx in slots_by_weekday:
            slots_by_weekday[idx].sort(key=lambda x: x[0])

        daily_plan = []

        for day_offset in range(self.max_days):
            current_date = today + timedelta(days=day_offset)
            day_slots = slots_by_weekday.get(current_date.weekday(), [])
            if not day_slots:
                continue

            total_available = int(sum(end - start for start, end in day_slots))
            day_items = []
            used_minutes = 0

            for start_m, end_m in day_slots:
                cursor = start_m
                while cursor < end_m and len(day_items) < 6:
                    pending = [r for r in remaining if r["remaining"] > 0]
                    if not pending:
                        break
                    pending.sort(key=lambda r: (r["deadline"], -r["remaining"]))
                    current_task = pending[0]

                    available_chunk = end_m - cursor
                    chunk = min(90, available_chunk, current_task["remaining"])
                    if chunk < 30:
                        break

                    task_obj = current_task["task"]
                    focus = (task_obj.detail or task_obj.name).strip()
                    day_items.append(
                        {
                            "task_name": task_obj.name,
                            "step": f"Step {current_task['step_idx']}: {focus}",
                            "minutes": int(chunk),
                            "scheduled_slot": f"{to_hhmm(cursor)}-{to_hhmm(cursor + chunk)}",
                        }
                    )

                    cursor += chunk
                    used_minutes += int(chunk)
                    current_task["remaining"] -= int(chunk)
                    current_task["step_idx"] += 1

            if day_items:
                daily_plan.append(
                    {
                        "date": current_date.strftime("%Y-%m-%d"),
                        "total_available_minutes": total_available,
                        "planned_minutes": int(min(used_minutes, total_available)),
                        "items": day_items,
                    }
                )

        unfinished = [r for r in remaining if r["remaining"] > 0]
        risk = "仍有任务未排满，建议增加空闲时段或延长计划窗口。" if unfinished else ""

        return {
            "summary": "已基于截止日期和可用时段生成可执行的基础计划。",
            "risk": risk,
            "need_more_info": False,
            "questions": [],
            "daily_plan": daily_plan,
            "notes": [],
        }

    def _merge_with_base(self, base_plan: dict, refined_plan: dict) -> dict:
        base_days = {d.get("date"): d for d in base_plan.get("daily_plan", []) if isinstance(d, dict)}
        refined_days = refined_plan.get("daily_plan", []) if isinstance(refined_plan.get("daily_plan", []), list) else []

        sanitized_days = []
        for day in refined_days:
            if not isinstance(day, dict):
                continue
            day_date = day.get("date")
            if day_date not in base_days:
                continue

            base_day = base_days[day_date]
            available = int(base_day.get("total_available_minutes", 0) or 0)
            raw_items = day.get("items", []) if isinstance(day.get("items", []), list) else []

            items = []
            used = 0
            for item in raw_items[:6]:
                if not isinstance(item, dict):
                    continue
                minutes = int(item.get("minutes", 0) or 0)
                if minutes <= 0:
                    continue
                if used + minutes > available:
                    minutes = max(0, available - used)
                if minutes <= 0:
                    break
                used += minutes
                items.append(
                    {
                        "task_name": str(item.get("task_name", "未命名任务")),
                        "step": str(item.get("step", "执行该任务")),
                        "minutes": minutes,
                        "scheduled_slot": str(item.get("scheduled_slot", "未指定时段")),
                    }
                )

            if items:
                sanitized_days.append(
                    {
                        "date": day_date,
                        "total_available_minutes": available,
                        "planned_minutes": used,
                        "items": items,
                    }
                )

        final_daily = sanitized_days if sanitized_days else base_plan.get("daily_plan", [])

        notes = []
        for source_notes in [base_plan.get("notes", []), refined_plan.get("notes", [])]:
            if isinstance(source_notes, list):
                for note in source_notes:
                    if isinstance(note, str) and note.strip():
                        notes.append(note.strip())

        return {
            "summary": refined_plan.get("summary") or base_plan.get("summary", ""),
            "risk": refined_plan.get("risk") or base_plan.get("risk", ""),
            "need_more_info": bool(refined_plan.get("need_more_info", False)),
            "questions": [q for q in refined_plan.get("questions", []) if isinstance(q, str) and q.strip()][:5],
            "daily_plan": final_daily,
            "notes": notes[:6],
        }
