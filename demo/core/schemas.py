from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class TaskInput:
    name: str
    detail: str
    estimated_minutes: Optional[int]
    deadline: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "detail": self.detail,
            "estimated_minutes": self.estimated_minutes,
            "deadline": self.deadline,
        }


@dataclass
class AvailabilityInput:
    weekday: str
    start: str
    end: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "weekday": self.weekday,
            "start": self.start,
            "end": self.end,
        }


def normalize_plan(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": raw.get("summary", ""),
        "risk": raw.get("risk", ""),
        "daily_plan": raw.get("daily_plan", []),
        "notes": raw.get("notes", []),
    }


def validate_tasks(tasks: List[TaskInput]) -> List[TaskInput]:
    return [t for t in tasks if t.name.strip() and t.deadline.strip()]


def validate_availability(slots: List[AvailabilityInput]) -> List[AvailabilityInput]:
    return [s for s in slots if s.start < s.end]
