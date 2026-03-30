import json
import socket
import time
from urllib import error, request


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 120,
        retry_count: int = 1,
        num_predict: int = 200,
        num_ctx: int = 2048,
        num_thread: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.retry_count = max(1, retry_count)
        self.num_predict = max(32, num_predict)
        self.num_ctx = max(512, num_ctx)
        self.num_thread = max(1, num_thread)
        self.last_metrics: dict = {
            "ok": False,
            "model": self.model,
            "elapsed_ms": None,
            "attempts": 0,
            "error": None,
            "endpoint": None,
        }

    def get_last_metrics(self) -> dict:
        return dict(self.last_metrics)

    def health(self) -> str:
        req = request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return "无法连接到本地 Ollama，请先执行 `ollama serve`。"

        models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
        if self.model in models:
            return f"Ollama 已连接，默认模型可用：{self.model}"
        return f"Ollama 已连接，但未找到默认模型：{self.model}（请执行 `ollama pull {self.model}`）"

    def _post_json(self, path: str, payload: dict, timeout_seconds: int | None = None) -> dict:
        req = request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=timeout_seconds or self.timeout_seconds) as resp:
            return json.loads(resp.read().decode("utf-8"))

    @staticmethod
    def _parse_json_text(model_text: str) -> dict:
        if not model_text:
            raise RuntimeError("模型没有返回内容")
        try:
            parsed = json.loads(model_text)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"模型返回不是合法 JSON: {model_text[:300]}") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError(f"模型返回 JSON 不是对象类型: {type(parsed).__name__}")
        return parsed

    def warmup(self, model: str | None = None, timeout_seconds: int = 12) -> dict:
        warm_model = model or self.model
        started = time.perf_counter()
        payload = {
            "model": warm_model,
            "stream": False,
            "prompt": "reply with ok",
            "options": {
                "temperature": 0,
                "num_predict": 8,
                "num_ctx": 512,
                "num_thread": self.num_thread,
            },
            "keep_alive": "30m",
        }
        try:
            self._post_json("/api/generate", payload, timeout_seconds=timeout_seconds)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": True, "model": warm_model, "elapsed_ms": elapsed_ms}
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {"ok": False, "model": warm_model, "elapsed_ms": elapsed_ms, "error": str(exc)}

    def chat_json(
        self,
        system_prompt: str,
        user_payload: dict,
        timeout_seconds: int | None = None,
        model: str | None = None,
    ) -> dict:
        user_payload_json = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))
        use_model = model or self.model

        options = {
            "temperature": 0.15,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
            "num_thread": self.num_thread,
        }

        chat_payload = {
            "model": use_model,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload_json},
            ],
            "options": options,
        }

        started = time.perf_counter()
        last_exc: Exception | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                result = self._post_json("/api/chat", chat_payload, timeout_seconds=timeout_seconds)
                model_text = (result.get("message") or {}).get("content", "").strip()
                if model_text:
                    parsed = self._parse_json_text(model_text)
                    self.last_metrics = {
                        "ok": True,
                        "model": use_model,
                        "elapsed_ms": int((time.perf_counter() - started) * 1000),
                        "attempts": attempt,
                        "error": None,
                        "endpoint": "/api/chat",
                    }
                    return parsed

                fallback_prompt = (
                    f"{system_prompt}\n"
                    "Return JSON only.\n"
                    f"User payload JSON:\n{user_payload_json}"
                )
                generate_payload = {
                    "model": use_model,
                    "stream": False,
                    "format": "json",
                    "keep_alive": "30m",
                    "prompt": fallback_prompt,
                    "options": options,
                }
                gen_result = self._post_json("/api/generate", generate_payload, timeout_seconds=timeout_seconds)
                gen_text = (gen_result.get("response") or "").strip()
                parsed = self._parse_json_text(gen_text)
                self.last_metrics = {
                    "ok": True,
                    "model": use_model,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "attempts": attempt,
                    "error": None,
                    "endpoint": "/api/generate",
                }
                return parsed
            except error.HTTPError as http_err:
                detail = http_err.read().decode("utf-8", errors="ignore")
                msg = f"Ollama HTTP 错误: {http_err.code} | {detail}"
                self.last_metrics = {
                    "ok": False,
                    "model": use_model,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "attempts": attempt,
                    "error": msg,
                    "endpoint": "/api/chat",
                }
                raise RuntimeError(msg) from http_err
            except (TimeoutError, socket.timeout, error.URLError) as exc:
                last_exc = exc
                if attempt < self.retry_count:
                    continue
                msg = (
                    f"调用 Ollama 超时（{timeout_seconds or self.timeout_seconds}s，重试 {self.retry_count} 次仍失败）。"
                )
                self.last_metrics = {
                    "ok": False,
                    "model": use_model,
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                    "attempts": attempt,
                    "error": msg,
                    "endpoint": "/api/chat",
                }
                raise RuntimeError(msg) from exc
            except Exception as exc:
                last_exc = exc
                break

        msg = f"调用 Ollama 失败: {last_exc}"
        self.last_metrics = {
            "ok": False,
            "model": use_model,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "attempts": self.retry_count,
            "error": msg,
            "endpoint": "/api/chat",
        }
        raise RuntimeError(msg)
