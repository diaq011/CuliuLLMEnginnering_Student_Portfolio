# Demo: 任务智能拆解与日程规划（Python Only）

本 Demo 已按模块化框架重建，并实现以下功能：

1. 首页有“开始制定计划”按钮。
2. 可输入任务（名称、内容、可选预计时长、截止日期）。
3. 可输入空闲时间段（周几、开始时间、结束时间）。
4. 连接本地 Ollama，输出按天拆解、可执行的计划（受空闲时段约束）。

## 目录结构（按此搭建）

```text
demo/
├─ README.md
├─ requirements.txt
├─ app.py
├─ core/
│  ├─ __init__.py
│  ├─ config.py
│  └─ schemas.py
├─ services/
│  ├─ __init__.py
│  ├─ ollama_client.py
│  └─ planner.py
└─ ui/
   ├─ __init__.py
   └─ components.py
```

## 模块说明

- `app.py`: Streamlit 入口，串联整体流程。
- `core/config.py`: 模型地址、模型名、周几配置等。
- `core/schemas.py`: 输入结构、基础校验、计划结果规范化。
- `services/ollama_client.py`: 本地 Ollama 健康检查与请求封装。
- `services/planner.py`: Prompt 构造与按天计划生成。
- `ui/components.py`: 页面组件与结果渲染。

## 输入格式

### tasks

```json
[
  {
    "name": "高数作业",
    "detail": "第3章习题 1-20",
    "estimated_minutes": 120,
    "deadline": "2026-03-31"
  }
]
```

### availability

```json
[
  {
    "weekday": "Monday",
    "start": "19:00",
    "end": "21:00"
  }
]
```

## 启动方式（必须用 streamlit）

1. 启动 Ollama

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

3. 打开页面

- `http://localhost:8501`

> 注意：不要用 `python demo\app.py` 启动，否则会出现 `missing ScriptRunContext` 提示。

## 可选环境变量

```powershell
$env:OLLAMA_URL="http://127.0.0.1:11434"
$env:OLLAMA_MODEL="qwen3:4b"
$env:OLLAMA_TIMEOUT_SECONDS="120"
$env:OLLAMA_RETRY_COUNT="1"
$env:OLLAMA_NUM_PREDICT="360"
$env:OLLAMA_NUM_CTX="4096"
$env:OLLAMA_NUM_THREAD="8"
$env:PLAN_MAX_DAYS="14"
streamlit run demo\app.py
```

## 速度优化建议

1. 优先使用更小模型测试

```powershell
ollama pull qwen2.5:3b
$env:OLLAMA_MODEL="qwen2.5:3b"
```

2. 控制生成长度（最有效）

- 将 `OLLAMA_NUM_PREDICT` 降到 `220-360`
- 将 `PLAN_MAX_DAYS` 控制在 `7-14`

3. 充分利用 CPU 线程

- Windows 下可设置：`$env:OLLAMA_NUM_THREAD="8"`（按你机器核心数调整）

4. 避免冷启动

- 先执行一次 `ollama run qwen3:4b "你好"`，再打开页面生成计划
