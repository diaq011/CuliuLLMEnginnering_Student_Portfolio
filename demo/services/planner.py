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
            "你是一个严谨的任务规划助手。"
            "必须根据用户给出的空闲时段安排任务，确保每天分配时长不超过可用时长。"
            "任务需要按截止日期优先级拆解成可执行步骤。"
            "默认按 30-90 分钟粒度拆分，避免过细拆解。"
            "输出必须是 JSON，且仅输出 JSON。"
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
                "给出从今天开始的按天计划，最多覆盖 planning_window.max_days 天",
                "每条计划写明日期、步骤、分钟数、安排时段；单日最多 3-6 条",
                "如果总任务超过可用时段，明确风险并给出删减优先级建议",
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

        # 发送前做 JSON 回环，确保传输给 Ollama 的是标准 JSON 数据结构。
        user_payload = json.loads(json.dumps(user_payload, ensure_ascii=False))

        raw = self.client.chat_json(system_prompt, user_payload)
        return normalize_plan(raw)
