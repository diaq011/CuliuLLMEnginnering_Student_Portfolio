# logs 使用说明

本目录用于存放运行日志、错误日志与观测指标。

建议包含：

- `run_log.jsonl/csv`：每次运行记录（输入、输出、耗时、错误码）
- `failure_log.md`：失败案例归档
- `runtime_metrics.json`：关键指标（成功率、失败率、平均延迟）

日志字段建议：

- `timestamp`
- `request_id`
- `query_or_task`
- `latency_ms`
- `error_code`
- `status`

最低提交标准：

1. 至少 1 份结构化运行日志
2. 至少 1 份失败案例归档文档
3. 可支持问题复盘与定位
