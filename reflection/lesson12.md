#### Didlist

1. Mission 1（E0） — 修复 MainAgentPlanner 中 `main_agent_state` 缺失问题
   - 改进 `prompts/main_agent_planner.md`（引导 LLM 输出具体字段）
   - 改进 `main_agent.py`（_starter_task_state 去 TODO、_normalize 逻辑修复、向后兼容保留 LLM 输出）
2. Mission 2（E3） — ResearchSubagent 返回结构化 evidence + Validator 拒绝坏结果
   - 改进 `prompts/research_subagent_executor.md`（指定 evidence_pack 结构化格式）
   - 实现 `validators.py` 的 `validate_subagent_result()`（source_id 追溯、Web evidence 完整、权限越界检查、citations 验证）
3. Mission 3（E4） — MainAgentExecutor 生成完整项目计划
   - 改进 `prompts/main_agent_executor.md`（强调用 resumed_task_state 指导输出）
   - 改进 `main_agent.py`（execute_final 传递 execution_context、_resume_task_state 丰富 _evidence_summary）
   - 实现 `validators.py` 的 `validate_final_output()`（检查 title/driving_question/hypothesis/steps/evidence_used）
4. 补充修复 — case_04 原始请求权限预检查
   - 在 `main_agent.py` 的 `run()` 方法中添加对原始 user_request 的权限风险关键词检查，在调用 subagent 之前就拦截

#### 知识点

- Agent 委托-恢复模式（Delegation-Resume Pattern）：MainAgent 规划→委托→恢复→执行
- LLM 提示词工程：JSON-only 输出、结构化字段引导、示例驱动
- 确定性代码 + LLM 混合架构：编排/验证/日志用代码控制，规划/生成交给 LLM
- 分级验证（Validation Pipeline）：委托协议验证 → 子 Agent 结果验证 → 最终输出验证
- SSE 流式传输：Flask + EventSource 实时展示管道各阶段
- 失败分类体系：failure_type（技术类）+ failure_category（教学框架 4+1 类）
- 数据库/持久化：JSONL 追加日志、JSON 静态配置
- Python 类型注解：`from __future__ import annotations` 联合类型