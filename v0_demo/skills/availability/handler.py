from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .constants import SKILL_NAME, SKILL_VERSION, WEEK_KEYS, WEEK_LABELS
from .parser import parse_availability_llm_response
from .prompt import AVAILABILITY_PARSE_SYSTEM_PROMPT


@dataclass
class AvailabilitySkillResult:
    reply: str
    applied: bool
    has_time_info: bool
    merge_mode: str
    polarity_trace: list[dict[str, str]] = field(default_factory=list)
    weekly_availability: dict[str, list[dict[str, str]]] | None = None
    skill: str = SKILL_NAME
    skill_version: str = SKILL_VERSION

    def to_api_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["weeklyAvailability"] = payload.pop("weekly_availability")
        return payload


class AvailabilitySkillHandler:
    """Natural-language weekly availability parser (Ollama primary, rule fallback on parse failure)."""

    def __init__(
        self,
        ollama_chat: Callable[[dict[str, Any]], dict[str, Any]],
        ollama_model: str,
    ) -> None:
        self._ollama_chat = ollama_chat
        self._ollama_model = ollama_model

    def build_chat_messages(
        self,
        history: list[dict[str, str]],
        current_availability: dict[str, list[dict[str, str]]],
        message: str,
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
        for item in history[-12:]:
            role = str(item.get("role", "")).strip()
            content = str(item.get("content", "")).strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        return messages

    def handle(
        self,
        message: str,
        current_availability: dict[str, list[dict[str, str]]],
        history: list[dict[str, str]] | None = None,
    ) -> AvailabilitySkillResult:
        text = str(message or "").strip()
        history = history or []

        ollama_messages = self.build_chat_messages(history, current_availability, text)
        llm_res = self._ollama_chat(
            {
                "model": self._ollama_model,
                "messages": ollama_messages,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                    "top_p": 0.1,
                },
            }
        )
        content = llm_res.get("message", {}).get("content", "{}")
        reply, normalized, has_time_info, merge_mode, polarity_trace = parse_availability_llm_response(
            content,
            current_availability,
            text,
        )
        return AvailabilitySkillResult(
            reply=reply,
            applied=normalized is not None,
            has_time_info=has_time_info,
            merge_mode=merge_mode,
            polarity_trace=polarity_trace,
            weekly_availability=normalized,
        )


def handle_availability_chat(
    message: str,
    current_availability: dict[str, list[dict[str, str]]],
    history: list[dict[str, str]] | None,
    ollama_chat: Callable[[dict[str, Any]], dict[str, Any]],
    ollama_model: str,
) -> AvailabilitySkillResult:
    return AvailabilitySkillHandler(ollama_chat, ollama_model).handle(
        message,
        current_availability,
        history,
    )
