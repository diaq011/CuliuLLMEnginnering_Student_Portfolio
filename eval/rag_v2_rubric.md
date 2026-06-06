# RAG v2 评测 Rubric

## 运行方式

```bash
cd v0_demo/backend && python3 test_knowledge_rag.py
```

用例定义见 [`rag_v2_eval_cases.json`](./rag_v2_eval_cases.json)。

## 通过标准

| 用例 | 检查项 | 通过条件 |
|------|--------|----------|
| 数学卷3张 | unit_count | = 3 |
| | p50 区间 | 280–380 min |
| | 模板匹配 | `tpl_math_test_paper_standard` |
| | 拆解 | ≥ 4 段 |
| 英语作文2篇 | unit_count | = 2 |
| | p50 区间 | 90–140 min |
| 背英语单词200个 | unit_count | = 200 |
| | p50 区间 | 70–110 min |
| | 拆解 | 4 批（每批约 50 词） |
| | 非回退 | ≠ 默认 60 min |

## 当前实测（2026-06-06）

| 任务 | p50 | 结果 |
|------|-----|------|
| 数学卷3张 | 375 min | 通过 |
| 英语作文2篇 | 105 min | 通过 |
| 背英语单词200个 | 106 min | 通过 |

## 失败记录模板

```markdown
### 任务：<标题>
- 预期 p50 区间：
- 实际 p50：
- 偏差原因：
- 修复动作：（调 unit_rate / template / 解析正则）
```
