# Availability Parser Skill Spec

| 项 | 值 |
|---|---|
| Skill 名称 | `availability-parser` |
| 版本 | v1.0 |
| 日期 | 2026-06-06 |
| 所属项目 | J人模拟器 — `v0_demo` |
| 运行时 | DeepSeek API（`DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL`，默认 `deepseek-chat`） |

---

## 1. 目的（Purpose）

用户用**自然语言**描述每周什么时候能学习。本 Skill 负责：

1. 判断输入是否包含可解析的**时间信息**
2. 识别每个时间片段是 **有空（available）** 还是 **没空（busy）**
3. **仅汇总有空时段**，输出标准 `weeklyAvailability` JSON
4. 「没空」只用于排除、不写入用户数据，**不单独持久化 busy 列表**

解析结果写入用户状态 `weeklyAvailability`，供 [`POST /api/plans/today`](../../backend/app.py) 计划排程使用。

---

## 2. 触发条件（When to invoke）

**应触发**

- 用户在「设置 → 空闲时间段设置 → AI 设置」聊天框输入
- 文本含：星期词、时间段、有空/没空/上课/补习等语义

**早退（不修改数据）**

- 输入不含任何可识别时间词 → `has_time_info: false`
- 示例：「我想设置一下」「怎么用这个功能」

---

## 3. 输入 Schema

```json
{
  "message": "工作日晚上7点到9点有空，周三晚上要上课没空",
  "current_weekly_availability": {
    "mon": [],
    "tue": [],
    "wed": [],
    "thu": [],
    "fri": [],
    "sat": [],
    "sun": []
  },
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `message` | 是 | 用户本轮自然语言 |
| `current_weekly_availability` | 是 | 当前已保存的 7 天空闲时段 |
| `history` | 否 | 最近对话（最多 12 轮） |

---

## 4. 输出 Schema

```json
{
  "has_time_info": true,
  "reply": "已理解：工作日 19:00-21:00 有空；周三晚上标记为没空，未写入空闲列表。",
  "merge_mode": "replace_all",
  "polarity_trace": [
    {"day": "mon", "start": "19:00", "end": "21:00", "polarity": "available"},
    {"day": "wed", "start": "19:00", "end": "21:00", "polarity": "busy"}
  ],
  "weekly_availability": {
    "mon": [{"start": "19:00", "end": "21:00"}],
    "tue": [{"start": "19:00", "end": "21:00"}],
    "wed": [],
    "thu": [{"start": "19:00", "end": "21:00"}],
    "fri": [{"start": "19:00", "end": "21:00"}],
    "sat": [],
    "sun": []
  }
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `has_time_info` | 是 | 是否检测到可解析时间 |
| `reply` | 是 | 给用户的中文确认 |
| `merge_mode` | 是 | `append` / `replace_mentioned_days` / `replace_all` |
| `polarity_trace` | 否 | 每条时间片段及 polarity，供调试/展示 |
| `weekly_availability` | 条件 | **仅含 available 时段**；7 天键必须齐全 |

### 4.1 day 枚举

| key | 中文 |
|-----|------|
| `mon` | 周一 |
| `tue` | 周二 |
| `wed` | 周三 |
| `thu` | 周四 |
| `fri` | 周五 |
| `sat` | 周六 |
| `sun` | 周日 |

### 4.2 时间格式

- `start` / `end`：`HH:MM`，24 小时制
- 结束时间必须晚于开始时间

### 4.3 merge_mode

| 值 | 触发语义 | 行为 |
|----|----------|------|
| `append` | 「还有」「再加」「另外」 | 在 `current` 上追加 available 时段 |
| `replace_mentioned_days` | 「把周一改成…」 | 仅清空并重写提到的日期 |
| `replace_all` | 首次设置、「全部重来」 | 覆盖整周（仍只写有空的时段） |

---

## 5. 处理流水线（Pipeline）

```
用户自然语言
  → [1] 时间词检测 → 无则 has_time_info=false 早退
  → [2] 抽取 day + start + end
  → [3] polarity 判定（available / busy）
  → [4] 过滤：仅保留 available
  → [5] 按 merge_mode 合并 current
  → [6] 校验 / 去重 / 排序
  → weekly_availability JSON
```

### Step 1 — 时间词检测

| 类型 | 示例 |
|------|------|
| 数字时间 | `7:00`、`19:00-21:00` |
| 中文时间 | `七点到九点`、`晚上七点半` |
| 星期 | `周一`、`工作日`、`周末` |
| 时段词 | `晚上`、`下午`、`放学后` |

### Step 2 — polarity 判定

**倾向 available**

- 有空、可以、能学、方便、空闲、有时间

**倾向 busy**

- 没空、忙、上课、补习、培训、有事、考试、排满

**规则**

- 同一片段若 busy 置信更高 → **不写入** `weekly_availability`
- 「除了周三晚上，工作日 7-9 点都有空」→ mon/tue/thu/fri 写入，wed 不写入该时段
- 默认：出现明确时间段且未出现 busy 词 → `available`

### Step 3 — 规范化

- 复用后端 `normalize_and_validate_availability`
- 同天重复 `{start,end}` 去重
- 时段按开始时间排序

---

## 6. LLM 集成

| 配置 | 默认值 |
|------|--------|
| `DEEPSEEK_API_KEY` | 必需 |
| `DEEPSEEK_API_URL` | `https://api.deepseek.com/v1` |
| `DEEPSEEK_MODEL` | `deepseek-chat` |
| `AVAILABILITY_DEEPSEEK_MODEL` | `deepseek-chat` |
| 接口 | `POST /v1/chat/completions`（OpenAI 兼容），`response_format.type: json_object` |

**LLM 输出要求**

- 只输出 JSON，无 markdown
- `changes` 每条可带 `polarity`；`weekly_availability` **不得含 busy 时段**
- 必须包含 `has_time_info`

**回退**

- LLM JSON 解析失败 → 规则解析 `extract_slots_from_user_message`（仅 available）
- DeepSeek API 不可用 → HTTP 503

---

## 7. API 衔接

**端点**：`POST /api/settings/availability/chat`

**请求**

```json
{"message": "...", "history": []}
```

**响应**

```json
{
  "reply": "...",
  "applied": true,
  "has_time_info": true,
  "merge_mode": "replace_all",
  "polarity_trace": [...],
  "weeklyAvailability": { "mon": [...], ... }
}
```

- `applied: false` 当 `has_time_info=false` 或解析/校验失败
- 持久化：`data/users/{username}_state.json` → `weeklyAvailability`

---

## 8. 示例用例

见 [`examples.json`](./examples.json)。

| # | 输入 | 期望 |
|---|------|------|
| 1 | 工作日晚上 7 点到 9 点有空 | mon–fri 各 `19:00-21:00` |
| 2 | 周一到周五 7-9 点有空，但周三晚上要上课 | wed 无该时段，其余四天有 |
| 3 | 还有周六下午 2 点到 5 点 | `merge_mode=append`，sat 追加 `14:00-17:00` |
| 4 | 我想设置一下 | `has_time_info=false`，不修改数据 |

---

## 9. 验收标准

- [ ] 含时间词时 `has_time_info=true` 且 `weekly_availability` 含 7 天键
- [ ] busy 描述不出现在最终 `weekly_availability`
- [ ] 与手动设置页 JSON 格式一致
- [ ] 计划生成 API 可直接读取 `weeklyAvailability`
- [ ] DeepSeek API 不可用时，简单「7点到9点」句式可规则回退

---

## 10. 非目标（v1 Out of Scope）

- 不存储 busy 黑名单表
- 不做跨时区
- 不解析具体日期（仅每周重复）
- ~~不使用云端模型~~（v1 已切换至 DeepSeek API）

---

## 11. 相关文件

| 文件 | 说明 |
|------|------|
| [`SKILL.md`](./SKILL.md) | Cursor Agent 调用说明 |
| [`handler.py`](./handler.py) | **Skill 入口**：`AvailabilitySkillHandler.handle()` |
| [`parser.py`](./parser.py) | 规则解析、polarity 过滤 |
| [`examples.json`](./examples.json) | 标准输入输出样例 |
| [`../../backend/app.py`](../../backend/app.py) | API 路由调用 handler |
