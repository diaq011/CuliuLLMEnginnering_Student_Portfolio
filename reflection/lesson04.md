1. 学到了什么
- 明确了 M1-M5 的完整开发路径：`建库 -> 检索 -> 生成 -> 引用 -> 前端联调`。
- 学会了 `metadata` 设计原则：只保留“可过滤 + 可回溯”的字段，避免冗余。
- 理解了 `document` 和 `metadata` 的分工：  
`document` 存诗歌正文，`metadata` 存结构化标签。
- 理解了 ChromaDB 的作用：存向量并做相似度检索，为生成提供证据。
- 实际搭建了接口契约：`/api/rag/health` 和 `/api/rag/ask`，并返回 `poem/citations/retrieved/query_vector`。
- 完成了最简前端闭环，能反复提问并看结果变化。
- 最有意思的就是学到了向量化这种神奇的东西

2. 遇到的问题
- `metadata` 是否要放 `content` 的困惑。
- 依赖缺失（`chromadb` 未安装）。
- Ollama 地址/端口错误（`11343` 与 `11434` 混淆）。
- 远端 Ollama 超时，导致 embedding/生成请求失败。
- 生成结果没有标题。
- 终端中文显示出现乱码（编码问题）。

3. 怎么解决的
- 把 `metadata` 精简为：`source/source_id/title/author/poem_type`。
- 安装依赖后重试脚本，保证 M2 可执行。
- 修正 Ollama 端口到 `11434`。
- 将 embedding 与 chat 地址分离：检索和生成各走独立配置，避免互相拖慢。
- 在生成逻辑里强制标题格式，并增加兜底 `《无题》`。
- 识别乱码是“终端显示编码”问题，不等于业务逻辑失败。
