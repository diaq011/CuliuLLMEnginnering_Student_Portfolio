from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, jsonify, request, send_from_directory

app = Flask(__name__)
store_lock = Lock()
FRONTEND_DIR = Path(__file__).resolve().parent.parent

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
OLLAMA_TIMEOUT_SEC = int(os.getenv("OLLAMA_TIMEOUT_SEC", "30"))

store: dict[str, Any] = {
    "tasks": [],
    "todayPlan": None,
    "checkins": [],
    "lastPlanner": "none",
}


def today_str() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def iso_now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    return response


@app.route("/api/<path:unused>", methods=["OPTIONS"])
def options_handler(unused: str):
    return ("", 204)


@app.route("/", methods=["GET"])
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/styles.css", methods=["GET"])
def styles():
    return send_from_directory(FRONTEND_DIR, "styles.css")


@app.route("/app.js", methods=["GET"])
def script():
    return send_from_directory(FRONTEND_DIR, "app.js")


@app.route("/assets/<path:filename>", methods=["GET"])
def assets(filename: str):
    return send_from_directory(FRONTEND_DIR / "assets", filename)


@app.route("/api/health", methods=["GET"])
def health():
    ok, msg = ollama_model_ready()
    return jsonify(
        {
            "ok": True,
            "time": iso_now(),
            "ollamaHost": OLLAMA_HOST,
            "ollamaModel": OLLAMA_MODEL,
            "ollamaModelReady": ok,
            "ollamaMessage": msg,
            "ollamaTimeoutSec": OLLAMA_TIMEOUT_SEC,
        }
    )


@app.route("/api/state", methods=["GET"])
def get_state():
    with store_lock:
        return jsonify(
            {
                "tasks": store["tasks"],
                "todayPlan": store["todayPlan"],
                "checkins": store["checkins"],
                "planner": store["lastPlanner"],
            }
        )


@app.route("/api/state/reset", methods=["POST"])
def reset_state():
    with store_lock:
        store["tasks"] = []
        store["todayPlan"] = None
        store["checkins"] = []
        store["lastPlanner"] = "none"
    return jsonify({"ok": True})


@app.route("/api/tasks", methods=["POST"])
def create_task():
    payload = request.get_json(silent=True) or {}
    title = str(payload.get("title") or "").strip()
    deadline = str(payload.get("deadline") or "").strip()
    estimated = payload.get("estimatedMinutes")

    if not title or not deadline:
        return jsonify({"message": "title and deadline are required"}), 400

    try:
        datetime.strptime(deadline, "%Y-%m-%d")
    except ValueError:
        return jsonify({"message": "deadline must be YYYY-MM-DD"}), 400

    if estimated is not None:
        try:
            estimated = int(estimated)
        except (TypeError, ValueError):
            return jsonify({"message": "estimatedMinutes must be an integer"}), 400
        if estimated <= 0:
            return jsonify({"message": "estimatedMinutes must be > 0"}), 400

    task = {
        "id": str(uuid4()),
        "title": title,
        "deadline": deadline,
        "estimatedMinutes": estimated,
        "status": "todo",
    }
    with store_lock:
        store["tasks"].append(task)

    return jsonify(task), 201


@app.route("/api/plans/today", methods=["POST"])
def build_today_plan():
    with store_lock:
        tasks = [task for task in store["tasks"] if task["status"] != "done"]

    if not tasks:
        return jsonify({"message": "请先添加至少一个任务，再生成今日计划"}), 400

    model_ok, model_msg = ollama_model_ready()
    if not model_ok:
        return jsonify({"message": f"Ollama 不可用：{model_msg}"}), 503

    try:
        plan = build_llm_plan(tasks)
        planner = f"ollama:{OLLAMA_MODEL}"
    except RuntimeError as exc:
        msg = str(exc)
        if "timed out" in msg.lower():
            return jsonify({"message": f"模型响应超时（{OLLAMA_TIMEOUT_SEC} 秒内未返回）"}), 504
        return jsonify({"message": f"模型调用失败：{msg}"}), 502
    except Exception as exc:
        return jsonify({"message": f"模型调用失败：{exc}"}), 502

    with store_lock:
        store["todayPlan"] = plan
        store["lastPlanner"] = planner

    return jsonify({"plan": plan, "planner": planner})


@app.route("/api/checkins", methods=["POST"])
def create_checkin():
    payload = request.get_json(silent=True) or {}
    task_id = str(payload.get("taskId") or "").strip()
    done = bool(payload.get("done", False))
    actual_minutes = payload.get("actualMinutes")

    if not task_id:
        return jsonify({"message": "taskId is required"}), 400

    if actual_minutes is not None:
        try:
            actual_minutes = int(actual_minutes)
        except (TypeError, ValueError):
            return jsonify({"message": "actualMinutes must be an integer"}), 400
        if actual_minutes <= 0:
            return jsonify({"message": "actualMinutes must be > 0"}), 400

    with store_lock:
        task = next((item for item in store["tasks"] if item["id"] == task_id), None)
        if task is None:
            return jsonify({"message": "taskId not found"}), 404
        task["status"] = "done" if done else "todo"
        checkin = {
            "taskId": task_id,
            "done": done,
            "actualMinutes": actual_minutes,
            "checkedAt": iso_now(),
        }
        store["checkins"].insert(0, checkin)

    return jsonify(checkin), 201


def build_llm_plan(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    prompt = make_planner_prompt(tasks)
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a study planning assistant. Return JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "format": "json",
    }
    res = ollama_chat(payload)
    content = res.get("message", {}).get("content", "")
    parsed = json.loads(content)

    allowed_ids = {task["id"] for task in tasks}
    raw_ids = parsed.get("taskIds", [])
    if not isinstance(raw_ids, list):
        raw_ids = []
    task_ids = [tid for tid in raw_ids if isinstance(tid, str) and tid in allowed_ids][:5]
    if not task_ids:
        task_ids = [task["id"] for task in sorted(tasks, key=lambda x: x["deadline"])[:5]]

    total = parsed.get("totalEstimatedMinutes")
    if not isinstance(total, int) or total <= 0:
        by_id = {task["id"]: task for task in tasks}
        total = sum((by_id[tid].get("estimatedMinutes") or 60) for tid in task_ids)

    return {"date": today_str(), "taskIds": task_ids, "totalEstimatedMinutes": total}


def make_planner_prompt(tasks: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "id": task["id"],
            "title": task["title"],
            "deadline": task["deadline"],
            "estimatedMinutes": task.get("estimatedMinutes") or 60,
        }
        for task in tasks
    ]
    return (
        f"today={today_str()}\n"
        "Select up to 5 tasks for today.\n"
        "Prioritize earlier deadlines and balanced workload.\n"
        "Output JSON: {\"taskIds\": string[], \"totalEstimatedMinutes\": integer}\n"
        f"tasks={json.dumps(normalized, ensure_ascii=False)}"
    )


def ollama_model_ready() -> tuple[bool, str]:
    req = Request(f"{OLLAMA_HOST}/api/tags", method="GET")
    try:
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        return False, f"cannot connect to Ollama: {exc}"
    except Exception as exc:
        return False, f"Ollama check failed: {exc}"

    names = {model.get("name") for model in data.get("models", [])}
    if OLLAMA_MODEL not in names:
        return False, f"model not found: {OLLAMA_MODEL}"
    return True, "ready"


def ollama_chat(payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"{OLLAMA_HOST}/api/chat",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=OLLAMA_TIMEOUT_SEC) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Ollama HTTP error: {exc.code}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT_SEC}s") from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, TimeoutError):
            raise RuntimeError(f"Ollama request timed out after {OLLAMA_TIMEOUT_SEC}s") from exc
        raise RuntimeError(f"Ollama unavailable: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Ollama returned non-JSON response") from exc


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
