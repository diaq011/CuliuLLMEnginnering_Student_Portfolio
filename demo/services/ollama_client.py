import json
import socket
from urllib import error, request


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int = 120,
        retry_count: int = 1,
        num_predict: int = 360,
        num_ctx: int = 4096,
        num_thread: int = 0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.retry_count = max(1, retry_count)
        self.num_predict = max(64, num_predict)
        self.num_ctx = max(1024, num_ctx)
        self.num_thread = max(0, num_thread)

    def health(self) -> str:
        req = request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return "无法连接到本地 Ollama，请先执行 ollama serve"

        models = [m.get("name", "") for m in data.get("models", []) if isinstance(m, dict)]
        if self.model in models:
            return f"Ollama 已连接，模型已就绪：{self.model}"
        return f"Ollama 已连接，但未找到模型：{self.model}（请先 ollama pull {self.model}）"

    def chat_json(self, system_prompt: str, user_payload: dict) -> dict:
        # 强制把用户侧 payload 序列化为 JSON 文本，保证传输格式一致。
        user_payload_json = json.dumps(user_payload, ensure_ascii=False, separators=(",", ":"))

        options = {
            "temperature": 0.2,
            "num_predict": self.num_predict,
            "num_ctx": self.num_ctx,
        }
        if self.num_thread > 0:
            options["num_thread"] = self.num_thread

        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload_json},
            ],
            "options": options,
        }

        req = request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_exc: Exception | None = None
        for attempt in range(1, self.retry_count + 1):
            try:
                with request.urlopen(req, timeout=self.timeout_seconds) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                model_text = (result.get("message") or {}).get("content", "").strip()
                if not model_text:
                    raise RuntimeError("模型没有返回内容")
                try:
                    parsed = json.loads(model_text)
                    if not isinstance(parsed, dict):
                        raise RuntimeError(f"模型返回 JSON 不是对象类型: {type(parsed).__name__}")
                    return parsed
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"模型返回不是合法 JSON: {model_text[:300]}") from exc
            except error.HTTPError as http_err:
                detail = http_err.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Ollama HTTP 错误: {http_err.code} | {detail}") from http_err
            except (TimeoutError, socket.timeout, error.URLError) as exc:
                last_exc = exc
                if attempt < self.retry_count:
                    continue
                raise RuntimeError(
                    f"调用 Ollama 超时（{self.timeout_seconds}s，重试{self.retry_count}次仍失败）。"
                    "建议先用更小任务测试，或提高 OLLAMA_TIMEOUT_SECONDS。"
                ) from exc
            except Exception as exc:
                last_exc = exc
                break

        raise RuntimeError(f"调用 Ollama 失败: {last_exc}")
