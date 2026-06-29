"""Chat-first study-planning agent.

This module is intentionally dependency-injected: it knows the DeepSeek tool
schema and how to run a multi-round tool-calling loop, but it does NOT touch
Flask, the data store, or the planner directly. The host (app.py) passes in:

- chat_fn(payload) -> raw DeepSeek response
- model: the model name to use
- dispatch_tool(name, args) -> (result_obj, changed_keys)

This keeps the agent reusable/testable and avoids circular imports.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from deepseek_client import extract_deepseek_message, extract_tool_calls

ASSISTANT_SYSTEM_PROMPT = (
    "你是「J人模拟器」的学习规划助手，服务高年级、学习任务重、不擅长自己排计划的学生。\n"
    "你的目标是让用户尽量用一句话、口语化地把事情交给你，而不用去点复杂的表单。\n"
    "你可以使用工具来真正地改变应用状态：\n"
    "- set_availability：当用户用自然语言描述空闲时间（如“工作日晚上7点到9点有空”）时调用。\n"
    "- add_task：当用户提到一个要做的任务和截止时间（如“数学卷3张周一前”）时调用，逐个任务调用。\n"
    "- generate_plan：当用户想要排计划/生成计划，或已录入任务且设置了空闲时间后，调用它生成跨天计划。\n"
    "- list_tasks / get_plan：当用户想查看已有任务或某天计划时调用。\n"
    "原则：\n"
    "1) 能用工具就用工具，不要假装已经保存。\n"
    "2) add_task 的 deadline 必须是 YYYY-MM-DD；如果用户说“周一前/明天”等相对时间，请根据 context 中的今天日期换算。\n"
    "3) 缺少必要信息（如任务没有截止日期）时，先用一句话追问，不要瞎编。\n"
    "4) 回复简洁、鼓励、口语化，使用中文。完成操作后用一两句话告诉用户你做了什么、下一步可以做什么。\n"
    "5) 如果用户只是闲聊或第一次使用，友好地介绍这个软件能帮他们做什么。"
)

# OpenAI-compatible tool schema consumed by DeepSeek function calling.
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "set_availability",
            "description": "把用户用自然语言描述的每周空闲时间解析并保存为状态。当用户提到自己什么时候有空时调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {
                        "type": "string",
                        "description": "用户原话或对其空闲时间的自然语言描述，例如：工作日晚上7点到9点有空，周末下午2点到5点。",
                    }
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "新增一个学习任务。每个任务调用一次。",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "任务名称，例如：数学卷3张"},
                    "deadline": {"type": "string", "description": "截止日期，格式 YYYY-MM-DD"},
                    "subject": {
                        "type": "string",
                        "description": "学科",
                        "enum": [
                            "chinese", "math", "english", "physics", "chemistry",
                            "biology", "history", "politics", "geography", "general",
                        ],
                    },
                    "taskType": {
                        "type": "string",
                        "description": "任务类型",
                        "enum": [
                            "test_paper", "exercise_set", "essay", "reading", "recitation",
                            "vocabulary", "mistake_review", "chapter_review", "preview",
                            "lab_report", "group_work", "presentation",
                        ],
                    },
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "medium", "hard"],
                        "description": "难度，默认 medium",
                    },
                    "estimatedMinutes": {
                        "type": "integer",
                        "description": "用户自评的预估时长（分钟），可选；不确定就不要填。",
                    },
                },
                "required": ["title", "deadline"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_plan",
            "description": "根据已录入的任务和已保存的空闲时间生成跨天学习计划。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "计划起始日期 YYYY-MM-DD，默认今天。",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "列出用户当前所有未完成/已录入的任务。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_plan",
            "description": "查看某一天已生成的学习计划。",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "日期 YYYY-MM-DD，默认今天。"}
                },
            },
        },
    },
]


def _parse_tool_args(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def run_agent_turn(
    chat_fn: Callable[[dict[str, Any]], dict[str, Any]],
    model: str,
    history: list[dict[str, str]],
    message: str,
    dispatch_tool: Callable[[str, dict[str, Any]], tuple[Any, list[str]]],
    context: dict[str, Any] | None = None,
    max_rounds: int = 4,
) -> dict[str, Any]:
    """Run one user turn through the agent, executing any requested tools.

    Returns {"reply": str, "stateChanged": {...}, "toolTrace": [...]}.
    `dispatch_tool(name, args)` must return (json-serializable result, changed_keys).
    """
    context = context or {}
    system_content = ASSISTANT_SYSTEM_PROMPT
    if context:
        system_content += "\n\ncontext（仅供你参考）：" + json.dumps(context, ensure_ascii=False)

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    for item in history[-12:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})

    state_changed: dict[str, bool] = {"tasks": False, "availability": False, "plan": False}
    tool_trace: list[dict[str, Any]] = []

    for round_index in range(max_rounds):
        is_last_round = round_index == max_rounds - 1
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if not is_last_round:
            payload["tools"] = TOOLS

        response = chat_fn(payload)
        assistant_msg = extract_deepseek_message(response)
        tool_calls = extract_tool_calls(response)

        if not tool_calls:
            reply = str(assistant_msg.get("content") or "").strip()
            return {"reply": reply, "stateChanged": state_changed, "toolTrace": tool_trace}

        # Echo the assistant message (with tool_calls) back into the conversation.
        messages.append(
            {
                "role": "assistant",
                "content": assistant_msg.get("content") or "",
                "tool_calls": tool_calls,
            }
        )

        for tc in tool_calls:
            fn = tc.get("function", {}) if isinstance(tc, dict) else {}
            name = str(fn.get("name") or "").strip()
            args = _parse_tool_args(fn.get("arguments"))
            try:
                result, changed = dispatch_tool(name, args)
            except Exception as exc:  # surface tool errors back to the model
                result, changed = {"error": str(exc)}, []
            for key in changed:
                if key in state_changed:
                    state_changed[key] = True
            tool_trace.append({"name": name, "args": args, "result": result})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )

    # Ran out of tool rounds: ask once more for a plain-text wrap-up.
    final = chat_fn({"model": model, "messages": messages, "stream": False})
    reply = str(extract_deepseek_message(final).get("content") or "").strip()
    return {"reply": reply, "stateChanged": state_changed, "toolTrace": tool_trace}
