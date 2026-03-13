# eval 使用说明

本目录用于存放评测数据、评测脚本与评测结果。

建议包含：

- `eval_sheet_v1.csv`：逐样本评测表（可从 `03_templates/eval_sheet_template.csv` 开始）
- `eval_set_v1.json/jsonl`：评测样本集
- `rag_rubric.md`：RAG 评分表（可从 `03_templates/rag_rubric_template.md` 开始）
- `eval_report_v1.md`：本轮评测结论与改进建议

最低提交标准：

1. 至少 1 份评测样本集
2. 至少 1 份可读的评测结果表
3. 至少 2 个失败案例及改进动作
