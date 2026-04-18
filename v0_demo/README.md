# v0_demo (Frontend + Flask Backend)

## 目录结构
- `index.html` / `styles.css` / `app.js`: 前端页面（静态资源）
- `backend/app.py`: Flask API

## 启动后端（局域网可访问）
在 `v0_demo/backend` 目录运行：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

默认监听：
- `APP_HOST=0.0.0.0`
- `APP_PORT=5000`

同一局域网设备访问地址：
- `http://<你的电脑IP>:5000/`

查询本机 IP（Windows）：
```powershell
ipconfig
```
查看当前网卡的 IPv4 地址（例如 `192.168.1.23`），然后在手机/平板浏览器访问：
`http://192.168.1.23:5000/`

## 可选环境变量
```powershell
set APP_HOST=0.0.0.0
set APP_PORT=5000
set OLLAMA_MODEL=qwen3:0.6b
set OLLAMA_HOST=http://127.0.0.1:11434
set OLLAMA_TIMEOUT_SEC=30
python app.py
```

## 已实现接口
- `GET /api/health`
- `GET /api/state`
- `POST /api/state/reset`
- `POST /api/tasks`
- `POST /api/plans/today`
- `POST /api/checkins`
