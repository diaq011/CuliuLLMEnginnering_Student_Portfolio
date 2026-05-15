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
