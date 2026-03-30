# Demo: 任务智能拆解与日程规划（性能优化版）

本 Demo 基于 `Streamlit + Ollama`，已完成：

1. 两阶段排程：先本地规则排骨架，再用 LLM 轻量润色。
2. 快速兜底：LLM 超时自动回退本地计划，保证页面可用。
3. 结果可观测：展示模式、模型、是否兜底、总耗时。
4. UI 重构：顶部步骤进度 + 左侧输入卡片 + 右侧时间线结果。

## 启动方式

1. 启动 Ollama 并拉取模型

```powershell
ollama serve
ollama pull qwen3:4b
```

2. 安装依赖并运行

```powershell
cd C:\Users\Computer\Documents\GitHub\CuliuLLMEnginnering_Student_Portfolio
pip install -r demo\requirements.txt
streamlit run demo\app.py
```

## 推荐环境变量

```powershell
$env:OLLAMA_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL_DEFAULT="qwen3:4b"
$env:OLLAMA_MODEL_QUALITY="qwen3:4b"
$env:OLLAMA_MODEL="qwen3:4b"
$env:OLLAMA_TIMEOUT_SECONDS="120"
$env:OLLAMA_FAST_TIMEOUT_SECONDS="12"
$env:OLLAMA_RETRY_COUNT="1"
$env:OLLAMA_NUM_PREDICT="200"
$env:OLLAMA_NUM_CTX="2048"
$env:OLLAMA_NUM_THREAD="8"
$env:PLAN_MAX_DAYS="14"
$env:UI_THEME="clean_productive_v1"
streamlit run demo\app.py
```

## 使用说明

1. 点击顶部 `开始制定计划`。
2. 填写任务清单与空闲时段。
3. 选择推理模式：
   - `极速模式（默认）`：更快返回。
   - `质量模式（更稳）`：使用更谨慎的润色策略。
4. 点击 `生成按天计划`。
5. 如首次较慢，可先点 `模型预热`。

## 输出结构

计划结果保持兼容：

```json
{
  "summary": "...",
  "risk": "...",
  "need_more_info": false,
  "questions": [],
  "daily_plan": [
    {
      "date": "YYYY-MM-DD",
      "total_available_minutes": 120,
      "planned_minutes": 100,
      "items": [
        {
          "task_name": "...",
          "step": "...",
          "minutes": 50,
          "scheduled_slot": "19:00-19:50"
        }
      ]
    }
  ],
  "notes": ["..."],
  "meta": {
    "mode": "llm_refined | local_fallback",
    "used_fallback": false,
    "model": "qwen3:4b",
    "llm_elapsed_ms": 800,
    "elapsed_ms_total": 980,
    "error": null
  }
}
```
