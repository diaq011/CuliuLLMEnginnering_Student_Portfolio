# RAG 知识库设计（v2 参数化模型）

> **当前生效文件**：[`v0_demo/backend/data/knowledge/task_knowledge_v2.jsonl`](../v0_demo/backend/data/knowledge/task_knowledge_v2.jsonl)  
> **Schema 示例**：[`schema.v2.example.json`](../v0_demo/backend/data/knowledge/schema.v2.example.json)  
> **生成脚本**：[`build_knowledge_v2.py`](../v0_demo/backend/data/knowledge/build_knowledge_v2.py)  
> **估时管线**：[`knowledge_rag.py`](../v0_demo/backend/knowledge_rag.py)

## 设计目标

v2 将知识库从「200 条孤立点估计」升级为 **任务认知模型**，后端先完成参数化估时，LLM 仅在证据包基础上微调（±15%）并排程。基准速度对准 **不擅长规划的 P 人学生**（`P_TYPE_SLOW_MULTIPLIER=1.18`）。

## 五层 record_type

| record_type | 数量 | 作用 |
|-------------|------|------|
| `ontology` | 12 | 任务类型别名、默认单位、数量正则 |
| `subject_profile` | 10 | 学科认知风格、P人学科乘子 |
| `unit_rate` | 44 | **单位速率**（可缩放），非整任务点估计 |
| `task_template` | 43 | 任务组成、拆解规则、排程约束 |
| `calibration_case` | 200 | 标定案例（校验用，非主查表） |
| `planning_rule` | 20 | 同日负荷、搭配禁忌、拆分策略 |

## 估时公式

```text
setup + units × rate_p50 × fatigue_batches × difficulty × grade × subject_mult × P_TYPE(1.18)
```

- `word` / `problem` / `page`：线性累加，疲劳按批（50词/10题/3页）计算
- `set` / `article` / `chapter`：逐单位疲劳系数

## 后端管线

```text
parse_task_intent → match_task_template → compute_parametric_estimate
  → retrieve_calibration_cases → build_evidence_package → LLM
```

环境变量：

- `P_TYPE_SLOW_MULTIPLIER`（默认 `1.18`）
- `ESTIMATE_PERCENTILE`（`p50` 或 `p75`）

## 评测用例

见 [`eval/rag_v2_eval_cases.json`](../eval/rag_v2_eval_cases.json)，运行：

```bash
cd v0_demo/backend && python3 test_knowledge_rag.py
```

---

## v1 遗留说明（仅供参考）

以下为 v1 扁平枚举式知识库的生成提示词，已由 v2 取代。旧文件保留于 `task_duration_knowledge.jsonl`。

# RAG 知识库生成提示词（v1 遗留）

下面这整份文档可以直接复制给一个**可以联网搜索的 AI**，让它生成适合本项目使用的 RAG 知识库。生成结果应保存为 JSONL 文件：

```text
v0_demo/backend/data/knowledge/task_duration_knowledge.jsonl
```

当前项目代码默认使用的 Ollama 模型是：

```text
qwen3:0.6b
```

项目名称是“J人模拟器”，目标用户是高年级、学习任务重、不擅长规划的学生。知识库的目标不是讲题或辅导知识点，而是帮助系统更准确估计学习任务耗时，并辅助把任务拆成每日可执行计划。

---

## 可直接复制的提示词

你是一个“学习任务耗时知识库构建助手”。请联网搜索公开资料，并结合常识、公开学习计划案例、作业量描述、学生时间管理资料，生成一个用于 RAG 检索的学习任务耗时知识库。

这个知识库用于一个叫“J人模拟器”的学习规划应用。用户会输入类似“数学卷3张”“英语作文2篇”“物理实验报告1份”“背英语单词200个”等任务和截止日期。系统需要根据知识库估计每类任务通常需要多久，再把任务拆成每天的学习计划。

请严格按照以下要求输出。

### 1. 输出格式

请输出 **JSONL**，也就是每一行都是一个完整 JSON 对象。不要输出 Markdown 表格，不要输出解释性段落，不要在 JSONL 前后添加额外说明。

每条记录代表一种“学习任务耗时模式”，而不是一篇长文章。

每条 JSON 必须是合法 JSON，字段名使用英文双引号，字符串使用双引号，不能有注释，不能有尾随逗号。

### 2. 生成数量

请生成 **200 条**知识库记录。

要求覆盖：

- 常见学科：语文、数学、英语、物理、化学、生物、历史、政治、地理、综合/其他。
- 常见任务类型：试卷、刷题、作文、阅读、背诵、单词、错题整理、章节复习、预习、实验报告、小组作业、PPT/展示。
- 难度：easy、medium、hard。
- 年级阶段：初中高年级、高中、中考/高考冲刺。

高频任务要多给样本，例如数学试卷、英语作文、单词背诵、理科刷题、错题整理、章节复习。

### 3. 单条记录 schema

每条记录必须包含以下字段：

```json
{
  "id": "math_test_paper_senior_high_medium_001",
  "subject": "math",
  "subject_label": "数学",
  "task_type": "test_paper",
  "task_type_label": "试卷",
  "grade_band": "senior_high",
  "difficulty": "medium",
  "work_unit": "page",
  "unit_count": 2,
  "estimated_minutes_min": 35,
  "estimated_minutes_max": 55,
  "estimated_minutes_p50": 45,
  "cognitive_load": "high",
  "recommended_split_minutes": 30,
  "suitable_time_block": ["evening", "weekend"],
  "tags": ["计算", "刷题", "限时训练"],
  "prerequisites": ["基础公式熟悉"],
  "description": "高年级学生完成数学试卷第1-2页，包含选择题和填空题。",
  "planning_advice": "优先安排在精力较好的整块时间，超过60分钟建议拆分。",
  "source_type": "public_case",
  "confidence": 0.75,
  "source_keywords": ["高中 数学 试卷 完成时间", "学习计划 数学刷题 时间"],
  "version": "2026-05-15"
}
```

### 4. 字段要求

#### id

稳定唯一 ID，格式：

```text
{subject}_{task_type}_{grade_band}_{difficulty}_{序号}
```

示例：

```text
math_test_paper_senior_high_medium_001
english_essay_exam_sprint_hard_003
```

只能使用小写英文字母、数字和下划线。

#### subject / subject_label

只能从以下枚举中选择：

```json
[
  {"subject": "chinese", "subject_label": "语文"},
  {"subject": "math", "subject_label": "数学"},
  {"subject": "english", "subject_label": "英语"},
  {"subject": "physics", "subject_label": "物理"},
  {"subject": "chemistry", "subject_label": "化学"},
  {"subject": "biology", "subject_label": "生物"},
  {"subject": "history", "subject_label": "历史"},
  {"subject": "politics", "subject_label": "政治"},
  {"subject": "geography", "subject_label": "地理"},
  {"subject": "general", "subject_label": "综合/其他"}
]
```

#### task_type / task_type_label

只能从以下枚举中选择：

```json
[
  {"task_type": "test_paper", "task_type_label": "试卷"},
  {"task_type": "exercise_set", "task_type_label": "习题/刷题"},
  {"task_type": "essay", "task_type_label": "作文/写作"},
  {"task_type": "reading", "task_type_label": "阅读"},
  {"task_type": "recitation", "task_type_label": "背诵"},
  {"task_type": "vocabulary", "task_type_label": "单词/词组"},
  {"task_type": "mistake_review", "task_type_label": "错题整理"},
  {"task_type": "chapter_review", "task_type_label": "章节复习"},
  {"task_type": "preview", "task_type_label": "预习"},
  {"task_type": "lab_report", "task_type_label": "实验报告"},
  {"task_type": "group_work", "task_type_label": "小组作业"},
  {"task_type": "presentation", "task_type_label": "展示/PPT"}
]
```

#### grade_band

只能从以下枚举中选择：

```json
["middle_high", "senior_high", "exam_sprint"]
```

含义：

- `middle_high`：初中高年级
- `senior_high`：高中
- `exam_sprint`：中考/高考冲刺

#### difficulty

只能从以下枚举中选择：

```json
["easy", "medium", "hard"]
```

含义：

- `easy`：重复性强、任务熟悉、阻力低。
- `medium`：普通作业、普通复习、普通输出任务。
- `hard`：新知识、高计算量、需要大量思考或产出文章/报告/展示。

#### work_unit

只能从以下枚举中选择：

```json
["problem", "page", "set", "section", "chapter", "article", "word", "paragraph", "item", "report", "slide", "deliverable", "minute"]
```

含义示例：

- `problem`：题目数量
- `page`：页数
- `set`：套数，例如一套卷子
- `article`：作文/文章篇数
- `word`：单词数量或作文字数
- `report`：报告数量
- `slide`：PPT 页数

#### unit_count

数字，表示本记录对应的单位数量。

示例：

- 10 道题：`work_unit = "problem"`，`unit_count = 10`
- 2 页卷子：`work_unit = "page"`，`unit_count = 2`
- 1 篇作文：`work_unit = "article"`，`unit_count = 1`
- 200 个单词：`work_unit = "word"`，`unit_count = 200`

#### estimated_minutes_min / estimated_minutes_max / estimated_minutes_p50

整数，单位为分钟。

要求：

- `estimated_minutes_min <= estimated_minutes_p50 <= estimated_minutes_max`
- 不要给极端夸张值。
- 估时应符合普通学生而不是顶尖学生。
- 如果资料不确定，用较宽区间表达不确定性。

#### cognitive_load

只能从以下枚举中选择：

```json
["low", "medium", "high"]
```

用于计划时避免同一天堆叠过多高负荷任务。

#### recommended_split_minutes

整数，建议单次拆分时长。

常见取值：

```json
[15, 20, 25, 30, 40, 45, 60]
```

原则：

- 低负荷任务可以较短。
- 高负荷任务建议 25-45 分钟拆分。
- 超过 60 分钟的任务应建议拆分。

#### suitable_time_block

数组，从以下枚举中选择 1-3 个：

```json
["morning", "afternoon", "evening", "weekend", "fragmented"]
```

含义：

- `morning`：适合早晨
- `afternoon`：适合下午
- `evening`：适合晚上
- `weekend`：适合周末整块时间
- `fragmented`：适合碎片时间

#### tags

数组，3-8 个关键词。应包含用户可能输入的中文词，例如：

```json
["数学卷", "选择题", "填空题", "刷题", "限时训练"]
```

#### prerequisites

数组，描述估时成立的前提。示例：

```json
["已经学过对应章节", "题目难度中等", "不包含详细订正"]
```

如果没有特殊前提，可以写：

```json
["无特殊前提"]
```

#### description

一句中文自然语言描述，便于 RAG 文本检索。必须包含：

- 年级阶段
- 学科
- 任务类型
- 工作量
- 难度或任务特点

示例：

```text
高中学生完成一篇中等难度英语作文，包括审题、列提纲、写作和简单修改。
```

#### planning_advice

一句中文建议，说明如何安排这个任务。示例：

```text
建议安排在精力较好的晚间整块时间，若超过45分钟可拆成构思和写作两段。
```

#### source_type

只能从以下枚举中选择：

```json
["public_case", "study_plan", "education_article", "general_estimate"]
```

含义：

- `public_case`：公开学习案例、经验贴、作业记录等
- `study_plan`：公开学习计划或时间安排
- `education_article`：教育类文章或资料
- `general_estimate`：综合常识推断

#### confidence

0 到 1 的数字。

建议：

- 资料依据较明确：0.75-0.9
- 资料一般但符合常识：0.6-0.75
- 主要靠综合估计：0.45-0.6

#### source_keywords

数组，列出你联网搜索时使用或建议核验的关键词。不要放 URL，放搜索关键词即可。

示例：

```json
["高中 英语作文 写作 时间", "高三 作文 训练 45分钟"]
```

#### version

固定写：

```text
2026-05-15
```

### 5. 覆盖比例要求

请尽量按以下比例生成 200 条：

- 数学：30 条
- 英语：30 条
- 语文：25 条
- 物理：20 条
- 化学：18 条
- 生物：15 条
- 历史：15 条
- 政治：15 条
- 地理：15 条
- 综合/其他：17 条

任务类型分布建议：

- `test_paper`：25 条
- `exercise_set`：35 条
- `essay`：18 条
- `reading`：18 条
- `recitation`：18 条
- `vocabulary`：15 条
- `mistake_review`：18 条
- `chapter_review`：20 条
- `preview`：10 条
- `lab_report`：8 条
- `group_work`：8 条
- `presentation`：7 条

难度分布建议：

- `easy`：约 25%
- `medium`：约 50%
- `hard`：约 25%

### 6. 质量要求

请确保：

1. 每条记录都是一行合法 JSON。
2. 所有枚举字段只能使用本文给定的枚举值。
3. `id` 不能重复。
4. `estimated_minutes_p50` 必须落在 min 和 max 之间。
5. 时间估计要符合普通学生，不要只按优秀学生速度估计。
6. 记录之间不要只是改 ID，必须有真实差异，例如学科、任务类型、单位数量、难度、建议拆分方式不同。
7. 不要生成课程讲解内容，不要讲具体题目解法。
8. 不要生成社交、好友、小组聊天相关功能内容。
9. 不要生成复杂成绩预测内容。
10. 输出必须只包含 JSONL 内容。

### 7. 生成前请先理解这些任务例子

用户可能输入：

```text
数学卷3张，周一前完成
英语作文2篇，周三前完成
物理实验报告1份，周五前完成
背英语单词200个，明天晚上前完成
整理化学错题30道，本周末前完成
复习历史一章，后天前完成
做地理选择题40道，今晚完成
语文阅读理解3篇，周日前完成
```

知识库记录要能帮助系统判断这类任务大概需要多久，并给出合理拆分建议。

### 8. 输出示例

最终输出应类似下面这样，但请生成完整 200 条：

```jsonl
{"id":"math_test_paper_senior_high_medium_001","subject":"math","subject_label":"数学","task_type":"test_paper","task_type_label":"试卷","grade_band":"senior_high","difficulty":"medium","work_unit":"page","unit_count":2,"estimated_minutes_min":35,"estimated_minutes_max":55,"estimated_minutes_p50":45,"cognitive_load":"high","recommended_split_minutes":30,"suitable_time_block":["evening","weekend"],"tags":["数学卷","选择题","填空题","刷题","限时训练"],"prerequisites":["已经学过对应章节","题目难度中等","不包含详细订正"],"description":"高中学生完成中等难度数学试卷第1-2页，主要包含选择题和填空题。","planning_advice":"建议安排在精力较好的整块时间，超过60分钟时拆成两段完成。","source_type":"public_case","confidence":0.75,"source_keywords":["高中 数学卷 完成时间","高三 数学刷题 计划"],"version":"2026-05-15"}
{"id":"english_essay_senior_high_medium_001","subject":"english","subject_label":"英语","task_type":"essay","task_type_label":"作文/写作","grade_band":"senior_high","difficulty":"medium","work_unit":"article","unit_count":1,"estimated_minutes_min":35,"estimated_minutes_max":60,"estimated_minutes_p50":45,"cognitive_load":"medium","recommended_split_minutes":45,"suitable_time_block":["afternoon","evening"],"tags":["英语作文","写作","审题","提纲","修改"],"prerequisites":["已明确题目要求","不包含精修润色"],"description":"高中学生完成一篇中等难度英语作文，包括审题、列提纲、写作和简单修改。","planning_advice":"建议先用10分钟列提纲，再用30-40分钟写作，避免和大量背诵任务堆叠。","source_type":"study_plan","confidence":0.72,"source_keywords":["高中 英语作文 写作 时间","高三 英语作文 训练 45分钟"],"version":"2026-05-15"}
```

---

## 生成后人工检查清单

把联网 AI 生成的 JSONL 保存前，至少检查：

- 是否正好 200 行。
- 是否每一行都是合法 JSON。
- 是否 `id` 没有重复。
- 是否枚举值都在本文允许范围内。
- 是否 `estimated_minutes_min <= estimated_minutes_p50 <= estimated_minutes_max`。
- 是否存在明显不合理耗时，例如“写一篇高中作文 5 分钟”或“背 20 个单词 3 小时”。
- 是否包含了本项目目标用户的常见任务，而不是大学论文、工作任务或课程教学内容。
# RAG Knowledge Base Design

## Current model

The runnable demo currently reads its Ollama chat model from `OLLAMA_MODEL`.
The default value in `v0_demo/backend/app.py` is:

```text
qwen3:0.6b
```

Download this model if you want to run the current code without changing
environment variables. The one-pager mentions `qwen3.5:4b`, but that is not the
current code default.

## Goal

The knowledge base should improve task duration estimation before the app has
enough personal history for a user. It should store small, structured examples
of common study tasks, their typical workload, and planning advice. The planner
can then retrieve the top_k most relevant examples and combine them with the
user's own check-in history.

User history should have higher priority than this general knowledge base,
because real personal completion time is the strongest signal.

## Storage format

Use JSONL for the first version: one JSON object per line.

Recommended path:

```text
v0_demo/backend/data/knowledge/task_duration_knowledge.jsonl
```

Each line should describe one estimate pattern, not a long article. Keep each
record focused so top_k retrieval can return precise evidence.

## Record schema

```json
{
  "id": "math_test_paper_senior_high_medium_001",
  "subject": "math",
  "subject_label": "数学",
  "task_type": "test_paper",
  "task_type_label": "试卷",
  "grade_band": "senior_high",
  "difficulty": "medium",
  "work_unit": "page",
  "unit_count": 2,
  "estimated_minutes_min": 35,
  "estimated_minutes_max": 55,
  "estimated_minutes_p50": 45,
  "cognitive_load": "high",
  "recommended_split_minutes": 30,
  "suitable_time_block": ["evening", "weekend"],
  "tags": ["计算", "刷题", "限时训练"],
  "prerequisites": ["基础公式熟悉"],
  "description": "高年级学生完成数学试卷第1-2页，包含选择题和填空题。",
  "planning_advice": "优先安排在精力较好的时间段，超过60分钟建议拆分。",
  "source_type": "interview",
  "confidence": 0.8,
  "version": "2026-05-15"
}
```

### Required fields

- `id`: Stable unique id. Use lowercase English words and numbers.
- `subject`: Normalized subject code.
- `subject_label`: Chinese display label.
- `task_type`: Normalized task type code.
- `task_type_label`: Chinese display label.
- `grade_band`: Student stage.
- `difficulty`: `easy`, `medium`, or `hard`.
- `work_unit`: Unit used by this record.
- `unit_count`: Number of units represented by this estimate.
- `estimated_minutes_min`: Lower bound.
- `estimated_minutes_max`: Upper bound.
- `estimated_minutes_p50`: Typical duration.
- `description`: Natural-language retrieval text.
- `planning_advice`: How the planner should schedule this task.
- `source_type`: Evidence source.
- `confidence`: 0.0 to 1.0 confidence score.

### Optional but recommended fields

- `cognitive_load`: `low`, `medium`, or `high`.
- `recommended_split_minutes`: Suggested maximum chunk size.
- `suitable_time_block`: `morning`, `afternoon`, `evening`, `weekend`,
  or `fragmented`.
- `tags`: Chinese or English keywords that users may type.
- `prerequisites`: Conditions that make the estimate valid.
- `version`: Date or version string for later cleanup.

## Classification tags

### Subjects

| Code | Label |
| --- | --- |
| `chinese` | 语文 |
| `math` | 数学 |
| `english` | 英语 |
| `physics` | 物理 |
| `chemistry` | 化学 |
| `biology` | 生物 |
| `history` | 历史 |
| `politics` | 政治 |
| `geography` | 地理 |
| `general` | 综合/其他 |

### Task types

| Code | Label | Typical units |
| --- | --- | --- |
| `test_paper` | 试卷 | `page`, `set`, `section` |
| `exercise_set` | 习题/刷题 | `problem`, `page` |
| `essay` | 作文/写作 | `article`, `word` |
| `reading` | 阅读 | `page`, `article` |
| `recitation` | 背诵 | `paragraph`, `page`, `item` |
| `vocabulary` | 单词/词组 | `word`, `item` |
| `mistake_review` | 错题整理 | `problem`, `page` |
| `chapter_review` | 章节复习 | `chapter`, `section` |
| `preview` | 预习 | `chapter`, `page` |
| `lab_report` | 实验报告 | `report` |
| `group_work` | 小组作业 | `deliverable`, `slide` |
| `presentation` | 展示/PPT | `slide`, `deliverable` |

### Grade bands

- `middle_high`: 初中高年级
- `senior_high`: 高中
- `exam_sprint`: 中考/高考冲刺
- `college_intro`: 大学低年级

### Difficulty

- `easy`: 熟悉、重复性强、低阻力任务。
- `medium`: 普通作业或复习任务。
- `hard`: 新知识、高计算量、需要输出文章/报告/展示的任务。

## Recommended amount

For an MVP, prepare 80-120 records:

- 8-10 subjects or subject groups.
- 8-12 common task types.
- At least 1-2 difficulty levels for the most common combinations.

For more stable top_k retrieval, prepare 200-300 records:

- Each common `subject + task_type + difficulty` combination should have 3-5
  records with different units or workload sizes.
- Include both high-confidence interview data and lower-confidence public cases.
- Add more records for high-frequency tasks such as math papers, English
  essays, vocabulary memorization, science exercise sets, and mistake review.

## Example records

```jsonl
{"id":"math_test_paper_senior_high_medium_001","subject":"math","subject_label":"数学","task_type":"test_paper","task_type_label":"试卷","grade_band":"senior_high","difficulty":"medium","work_unit":"page","unit_count":2,"estimated_minutes_min":35,"estimated_minutes_max":55,"estimated_minutes_p50":45,"cognitive_load":"high","recommended_split_minutes":30,"suitable_time_block":["evening","weekend"],"tags":["计算","刷题","限时训练"],"prerequisites":["基础公式熟悉"],"description":"完成数学试卷第1-2页，主要是选择题和填空题。","planning_advice":"安排在精力较好的整块时间，超过60分钟拆成两段。","source_type":"interview","confidence":0.8,"version":"2026-05-15"}
{"id":"english_essay_senior_high_medium_001","subject":"english","subject_label":"英语","task_type":"essay","task_type_label":"作文","grade_band":"senior_high","difficulty":"medium","work_unit":"article","unit_count":1,"estimated_minutes_min":35,"estimated_minutes_max":60,"estimated_minutes_p50":45,"cognitive_load":"medium","recommended_split_minutes":45,"suitable_time_block":["afternoon","evening"],"tags":["作文","写作","范文"],"prerequisites":["已明确题目要求"],"description":"完成一篇高中英语作文，包括构思、初稿和简单修改。","planning_advice":"可先安排10分钟列提纲，再安排30-40分钟写作。","source_type":"interview","confidence":0.75,"version":"2026-05-15"}
{"id":"general_mistake_review_senior_high_easy_001","subject":"general","subject_label":"综合","task_type":"mistake_review","task_type_label":"错题整理","grade_band":"senior_high","difficulty":"easy","work_unit":"problem","unit_count":10,"estimated_minutes_min":25,"estimated_minutes_max":45,"estimated_minutes_p50":35,"cognitive_load":"medium","recommended_split_minutes":30,"suitable_time_block":["fragmented","evening"],"tags":["错题","复盘","订正"],"prerequisites":["已有错题记录"],"description":"整理10道错题，包含订正、原因标注和同类题提醒。","planning_advice":"适合拆成较短时段，避免和大量新题堆在同一天。","source_type":"public_case","confidence":0.65,"version":"2026-05-15"}
```

## Retrieval recommendation

For the first RAG implementation:

1. Parse the user task into rough `subject`, `task_type`, `unit_count`, and
   `difficulty`.
2. Filter records by `subject`, `task_type`, and `grade_band` when possible.
3. Score remaining records with:
   - text similarity between user task and `description/tags`;
   - unit count closeness;
   - confidence;
   - user history boost when matching personal check-in samples exist.
4. Return the top_k records as evidence.
5. Ask the LLM to cite the returned `id` values when producing estimates.

Suggested default:

```text
top_k = 5
```
