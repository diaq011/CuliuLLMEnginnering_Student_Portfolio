1. Trace / Span 可观测性
给每次请求生成 trace_id，给每个步骤记录 span，方便知道问题发生在 input、planner、tool、memory、skill 还是 output。

2. Safety Guardrail
增加三层安全检查：
input_guard 拦截攻击输入，tool_guard 检查工具调用，output_guard 防止输出完整答案或越界内容。

3. Fallback 兜底机制
当 planner、tool、memory、skill/output 出问题时，不直接崩溃，而是给出安全、诚实的降级回答，并留下证据。

