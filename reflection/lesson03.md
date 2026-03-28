#### didList:
1. 切换到你指定目录并读取 handout  
- 在 `C:\Users\Computer\Desktop\game_suggester` 下工作。  
- 读取了 `student_handout.md`，确认了任务2和任务3的要求。

2. 完成任务1的数据准备（你之前要求的）  
- 生成了 15 条评测样本 JSON，覆盖：
  - 中局常见局面
  - 稀疏/密集盘面
  - 含 `X` 局面
  - 非标准尺寸局面  
- 已写入 `testData`（以及你当前结构里的 `testingPrompt/testingData` 也已有同批样本）。

3. 完成任务2计划文档  
- 已输出计划文档：  
  - [eval_plan.md](C:\Users\Computer\Desktop\game_suggester\testingPrompt\testingPlan\eval_plan.md)  
- 计划中明确了：
  - 单变量控制（只改 `prompt_version`）
  - 样本分层
  - 评测维度和判定标准
  - 记录字段结构
  - 执行步骤

4. 进入任务3并做了实现准备  
- 新增了迭代版 Prompt：  
  - [few_shot_v2.md](C:\Users\Computer\Desktop\game_suggester\prompt_versions\few_shot_v2.md)
- 新增了评测脚本：  
  - [run_task3_eval.py](C:\Users\Computer\Desktop\game_suggester\testingPrompt\testingReport\run_task3_eval.py)
- 脚本功能包括：
  - 跑 `zero_shot / one_shot / few_shot / few_shot_v2`
  - 读统一样本 + 本组样本
  - 计算 `format_ok / usable / legal_pass_rate / reason_quality / stability`
  - 输出 `CSV + MD + failure_cases.json` 到 `testingPrompt/testingReport`
- 修复了样本读取 BOM 编码问题（改为 `utf-8-sig`）。

5. 按你要求增强“运行过程可见性”  
- 给评测脚本加了分阶段实时日志和进度百分比输出。  
- 已通过语法检查（`py_compile` 成功）。

6. 正在运行评测分析当中。。。

#### 收获
1. 了解利用ai工具辅助开发时的各种注意事项有了更深入的了解
2. 对整体流程和ai辅助开发的形式更为熟悉
3. 得到了一个codex会员