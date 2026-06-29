# 开发日志（Development Log）

> **用途**：记录项目每次功能更新与重要决策，便于对话过长时在新会话里让 AI 快速了解项目历史。  
> **维护约定**：每完成一轮开发，在「最新更新」追加一条；格式见文末模板。  
> **相关文档**：`[project_one_page.md](./project_one_page.md)`（项目定义）、`[rag_knowledge_base_design.md](./rag_knowledge_base_design.md)`（知识库设计）

---

## 给 AI 的快速上下文（Handoff Snapshot）


| 项         | 说明                                                                                                     |
| --------- | ------------------------------------------------------------------------------------------------------ |
| 项目名称      | J人模拟器 — 面向高年级学生的学习计划工具                                                                                 |
| 主代码目录     | `v0_demo/`（前端 HTML/CSS/JS + Flask 后端）                                                                  |
| 后端入口      | `v0_demo/backend/app.py`                                                                               |
| 前端入口      | `v0_demo/index.html` + `app.js` + `styles.css`（默认进入「对话」页）                                              |
| 默认 LLM    | DeepSeek `deepseek-chat`（OpenAI 兼容，`v0_demo/backend/deepseek_client.py`，环境变量 `DEEPSEEK_API_KEY` 等）    |
| 对话 Agent  | `v0_demo/backend/assistant_agent.py`（function calling）+ `POST /api/chat`                              |
| 知识库文件     | `v0_demo/backend/data/knowledge/task_knowledge_v2.jsonl`（v2 参数化；v1 遗留 `task_duration_knowledge.jsonl`） |
| 本地启动      | `cp run.local.sh.example run.local.sh` 填入 key 后 `./run.local.sh`（默认 5001，macOS 5000 常被 AirPlay 占用）    |
| 账号        | 可选：默认免登录（游客 `X-Guest-Id` 头，状态持久化到 `data/users/guest_<id>_state.json`），登录后用账号态                          |
| 当前 MVP 范围 | AI 对话主页（录任务/设空闲/生成计划/查询）、时间轴、计划列表、专注模式、账号、RAG 估时                                                       |


**尚未实现 / 后续阶段**：流式输出、游客→账号状态迁移、ChromaDB 向量检索、桌面小组件、手机使用监督、语音录入。

---

## 最新更新

### 2026-06-28 — 架构改造：AI 对话主页 + 全能 Agent + 账号可选

**做了什么**

- 前端主体改为 AI 对话窗口：新增 `data-page="chat"` 页与底部导航「对话」项，并设为默认进入页（[v0_demo/index.html](../v0_demo/index.html)、[v0_demo/app.js](../v0_demo/app.js)）。新用户首次进入由前端 seed 一条介绍消息（`ASSISTANT_INTRO`），历史存 `localStorage`。
- 新增对话 Agent：`POST /api/chat` 跑多轮 function calling 循环，DeepSeek 通过工具真正修改应用状态。工具：`set_availability`/`add_task`/`generate_plan`/`list_tasks`/`get_plan`（[v0_demo/backend/assistant_agent.py](../v0_demo/backend/assistant_agent.py)）。返回 `reply` + `stateChanged`，前端据此刷新时间轴/计划/空闲时间。
- 账号改为可选（降低门槛）：`get_current_username` 无 token 时回退 `X-Guest-Id` 游客态；`api()` 注入该头；前端门禁由 `hasIdentity()` 取代「必须登录」，退出后自动转游客。
- DeepSeek 客户端支持 function calling：`deepseek_chat` 透传 `tools`/`tool_choice`，新增 `extract_tool_calls` / `extract_deepseek_message`。
- 计划生成核心抽成可复用的 `run_plan_generation(username, date)`（`PlanGenerationError` 承载消息+状态码），供 HTTP 路由与 Agent 共用。
- 安全：API key 不入库，改由 gitignored 的 `v0_demo/backend/run.local.sh` 注入（附 `.example` 模板），`.gitignore` 增加 `*.local.*`。

**为什么**

- 原四页+表单对新用户门槛过高；改为「一句话交给 AI」更易上手，符合"每天≤5分钟"的成功标准。

**涉及文件**

- `v0_demo/backend/assistant_agent.py`（新）、`v0_demo/backend/app.py`、`v0_demo/backend/deepseek_client.py`
- `v0_demo/index.html`、`v0_demo/app.js`、`v0_demo/styles.css`
- `v0_demo/backend/run.local.sh(.example)`、`.gitignore`

**验证方式**

- `assistant_agent.run_agent_turn` mock 单测通过；起服务实测对话一次完成「设空闲+加任务+生成计划」三次工具调用，状态持久化到游客 state，时间轴出现排程方块。

---

### 2026-06-06 — 空闲时段解析 Skill（availability-parser）

**Skill 文档**

- `v0_demo/skills/availability/availabilitySkillSpec.md` — 完整 spec
- `SKILL.md` + `examples.json`

**后端升级**

- Skill 模块化：`v0_demo/skills/availability/handler.py`（`AvailabilitySkillHandler`）
- `app.py` 路由 `/api/settings/availability/chat` 调用 handler，连接本地 Ollama
- `has_time_info` 早退；`polarity_trace` + busy 过滤

---

### 2026-06-06 — RAG 知识库 v2 参数化重构

**知识库五层结构**

- `ontology` / `subject_profile` / `unit_rate` / `task_template` / `calibration_case` / `planning_rule`
- 新文件 `task_knowledge_v2.jsonl`（329 条），生成脚本 `build_knowledge_v2.py`
- Schema 示例 `schema.v2.example.json`；设计文档更新 `rag_knowledge_base_design.md`

**后端估时管线（混合模式）**

- 新模块 `knowledge_rag.py`：`parse → match → compute → package`
- 单位速率可缩放（如「数学卷3张」= 3×套卷速率×疲劳×P人系数 1.18）
- `word`/`problem` 线性累加、按批疲劳；`set`/`article` 逐单位疲劳
- LLM 以 `evidence_package.parametric_estimate` 为基准，允许 ±15% 微调

**评测**

- `eval/rag_v2_eval_cases.json` + `eval/rag_v2_rubric.md`
- `test_knowledge_rag.py` 三组课堂样本全部通过

**涉及文件**

- `v0_demo/backend/knowledge_rag.py`、`app.py`
- `v0_demo/backend/data/knowledge/task_knowledge_v2.jsonl`、`build_knowledge_v2.py`

---

### 2026-06-06 — 空闲时段 AI 设置 + 追加合并修复 + 开发日志

**空闲时段设置（三级导航）**

- 设置 → 空闲时间段设置 → **AI 设置** / **手动设置**
- **手动设置**：保留逐天编辑界面（周一～周日，可添加多个时段）
- **AI 设置**：聊天式界面，自然语言描述空闲时间，后端 Ollama 解析并保存

**后端 API**

- `POST /api/settings/availability/chat`：解析用户描述，写入 `weeklyAvailability`
- 支持 `merge_mode`：`append`（追加）、`replace_mentioned_days`、`replace_all`
- 修复 bug：用户说「还有 7 点到 8 点」时，不再覆盖已有 19:00–21:00，而是合并多个时段
- 模型漏解析时，后端从中文原话兜底提取时间（如「七点钟到八点钟」）

**计划生成**

- 时间不足时弹窗提示；计划详情中展示缺口时长与受影响任务（`details.timeShortage`）

**文档**

- 新增本文件 `docs/DEVELOPMENT_LOG.md`

**涉及文件**

- `v0_demo/index.html`、`v0_demo/app.js`、`v0_demo/styles.css`
- `v0_demo/backend/app.py`

---

## 历史记录

### 2026-06（早些时候）— UI 优化、RAG、专注、账号

**前端 UI**

- 背景图铺满全屏（`body` 层 + 渐变备用），消除黑边
- 卡片/弹窗真实半透明 + `backdrop-filter` 磨砂
- 按钮圆角、hover/active/focus 像素风交互
- 底部导航换 assets 图标；时间轴缩放、重叠方块紧凑布局
- 删除多余 hint 文案（如「点击方块可编辑」「全部任务」等）

**设置页**

- 分类列表结构：空闲时间、账号、专注
- 修复空闲时段输入框默认不可见的问题

**任务与计划**

- 任务表单增加学科 / 任务类型 / 难度下拉（与知识库字段对齐）
- 计划列表默认显示任务列表，右上角按钮进入创建页
- 任务三点菜单：编辑、删除；任务变更后时间轴显示「未重新生成」红字
- 时间轴固定高度、从有内容时间起显示；方块可点击编辑/删除

**RAG**

- 知识库 JSONL：`task_duration_knowledge.jsonl`（约 200 条）
- 设计文档：`docs/rag_knowledge_base_design.md`
- 后端 `compute_knowledge_rag_examples`：结构化 + 文本相似度 top_k，与用户历史样本合并

**专注模式**

- 主页「计时器」改为「专注」；全屏专注界面、可最小化为悬浮球、可设置显示模式
- 结束专注后在时间轴添加方块

**账号**

- 登录移至右上角图标；设置内账号分类展示资料/退出
- 暂不支持自定义头像上传

---

### 2026-05 — 核心功能成型


| 日期/提交     | 内容                                  |
| --------- | ----------------------------------- |
| 跨天计划      | 计划可拆分到 DDL 前多天，按空闲时段排程              |
| 空闲时间段     | 每周可用时段配置，参与计划生成                     |
| 账号系统      | 注册/登录，用户状态隔离（JSON 文件）               |
| Ollama 集成 | 计划生成走 `qwen3:0.6b`；RAG top_k 用户历史样本 |
| 局域网       | 支持局域网访问 demo                        |
| UI 美化     | 像素风背景、卡片布局初版                        |


---

### 更早 — 项目启动

- 初始化仓库与 `docs/project_one_page.md` 项目定义
- `v0_demo` 初步框架：任务 CRUD、今日计划、打卡
- 解决 Ollama 连接与模型响应过慢问题
- 添加 lesson reflection 与 PPT 设计稿等课程文档

---

## 关键 API 一览


| 方法         | 路径                                     | 说明                 |
| ---------- | -------------------------------------- | ------------------ |
| POST       | `/api/chat`                            | AI 对话 Agent（function calling 驱动录任务/设空闲/出计划） |
| POST       | `/api/auth/register` `/api/auth/login` | 账号                 |
| GET/POST   | `/api/tasks`                           | 任务列表 / 创建          |
| PUT/DELETE | `/api/tasks/<id>`                      | 编辑 / 删除任务          |
| GET/POST   | `/api/settings/availability`           | 读取 / 保存空闲时段        |
| POST       | `/api/settings/availability/chat`      | AI 解析空闲时段          |
| POST       | `/api/plans/today`                     | 生成今日计划             |
| GET        | `/api/plans/<date>`                    | 按日期取计划             |
| POST       | `/api/checkins`                        | 任务打卡               |
| GET        | `/api/health`                          | 健康检查（含 DeepSeek 可用性与模型名） |


---

## 已知问题与备忘

1. **端口 5000**：macOS AirPlay（ControlCenter）常占用，`run.local.sh` 默认 `APP_PORT=5001`
2. **API Key**：DeepSeek key 仅放在 gitignored 的 `run.local.sh`，切勿提交；若曾泄露请到 DeepSeek 控制台吊销重置
3. **模型行为**：偶尔 Agent 已成功生成计划却在回复里表述为"失败"，属模型措辞问题，状态已正确落库
4. **向量检索**：知识库当前为属性 + 文本相似度，尚未接 ChromaDB
5. **游客态**：游客状态按 `X-Guest-Id` 持久化，暂不自动迁移到账号
6. **Cloud vs Local**：在 Cursor Cloud 改的文件需同步到本地仓库后再运行

---

## 追加条目模板（复制到「最新更新」上方）

```markdown
### YYYY-MM-DD — 简短标题

**做了什么**
- ...

**为什么**
- ...

**涉及文件**
- ...

**验证方式**
- ...
```

---

*最后维护：2026-06-28*