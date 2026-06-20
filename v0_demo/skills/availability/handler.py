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
    """Natural-language weekly availability parser (DeepSeek/LLM primary, rule fallback on parse failure)."""

    def __init__(
        self,
        llm_chat: Callable[[dict[str, Any]], dict[str, Any]],
        llm_model: str,
        is_deepseek: bool = False,
    ) -> None:
        self._llm_chat = llm_chat
        self._llm_model = llm_model
        self._is_deepseek = is_deepseek

    def _extract_content(self, llm_response: dict[str, Any]) -> str:
        """Extract content from LLM response, supporting both DeepSeek and Ollama formats."""
        if self._is_deepseek:
            try:
                return llm_response["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise RuntimeError(f"Unexpected LLM API response structure: {exc}") from exc
        else:
            return llm_response.get("message", {}).get("content", "{}")

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

        llm_messages = self.build_chat_messages(history, current_availability, text)

        # Build payload compatible with both Ollama and DeepSeek
        payload: dict[str, Any] = {
            "model": self._llm_model,
            "messages": llm_messages,
            "stream": False,
            "format": "json",
        }

        # DeepSeek supports temperature/top_p via OpenAI-compatible params
        if self._is_deepseek:
            payload["options"] = {
                "temperature": 0,
                "top_p": 0.1,
            }

        llm_res = self._llm_chat(payload)
        content = self._extract_content(llm_res)
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
    llm_chat: Callable[[dict[str, Any]], dict[str, Any]],
    llm_model: str,
    is_deepseek: bool = False,
) -> AvailabilitySkillResult:
    return AvailabilitySkillHandler(llm_chat, llm_model, is_deepseek).handle(
        message,
        current_availability,
        history,
    )
