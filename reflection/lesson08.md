## didList
- 先扫描 skills/，把每个 SKILL.md 读成 registry。
- 用本地 Ollama qwen3:0.6b 根据用户请求选择 skill。
- 路由成功后执行对应 handler.py。
- 用 Flask 做了一个网页聊天界面。
- 前端默认展示自然语言回答，把 router result / skill input / skill output 放到“过程详情”里。

## 学到了什么
- Router 不是直接回答问题，而是判断“该用哪个 skill”。
- SKILL.md 是 skill 的说明书，也是 router 判断依据。
- 小模型会犯错，所以要加 clarification、fallback 和结果校验。
- LLM 输出 JSON 不稳定，后端必须做容错。
- 好界面应该先给用户看答案，调试细节要隐藏起来。