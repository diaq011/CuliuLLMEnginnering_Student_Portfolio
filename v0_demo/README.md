# v0_demo (Frontend + Flask Backend)

## 目录结构
- `index.html` / `styles.css` / `app.js`: 前端页面（静态）
- `backend/app.py`: Flask API

## 启动后端
在 `v0_demo/backend` 目录运行：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

后端地址：`http://127.0.0.1:5000`

默认模型是 `qwen3:0.6b`。可通过环境变量修改：

```bash
set OLLAMA_MODEL=qwen3:0.6b
set OLLAMA_HOST=http://127.0.0.1:11434
python app.py
```

## 打开前端
推荐直接访问：`http://127.0.0.1:5000/`（由 Flask 提供前端页面）。

也可以双击打开 `v0_demo/index.html`，前端会回落到 `http://127.0.0.1:5000/api`。

## 已实现接口
- `GET /api/health`
- `GET /api/state`
- `POST /api/tasks`
- `POST /api/plans/today`
- `POST /api/checkins`
