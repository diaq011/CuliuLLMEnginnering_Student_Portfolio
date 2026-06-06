#### didList

1. 读懂 L10 baseline  
   梳理了 `planner.py`、`executor.py`、`state_manager.py`，明确 Planner 负责计划，Executor 负责执行，State 负责传递中间结果。

2. 完成 L10 扩展  
   加入了 `memory_read`、`tool_call`、`memory_write`，让 agent 能读记忆、查洛谷题目、写回学习状态。

3. 做成可运行网页 demo  
   新增 Flask 后端和 HTML 前端，可以输入请求，查看 plan、run log、state 和最终回答。

#### 收获

- Agent 架构：Planner / Executor / State
- Tool 调用与 Memory 读写
- execution plan 与 step_type
- Flask API
- HTML + fetch 前后端交互
- 本地 Ollama 调用
- JSON 解析与容错
- 结构化输出转自然语言回答