#!/usr/bin/env python3
"""Generate task_knowledge_v2.jsonl from structured layer definitions."""

from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).resolve().parent / "task_knowledge_v2.jsonl"
OLD = Path(__file__).resolve().parent / "task_duration_knowledge.jsonl"
P_TYPE = 1.18

TASK_TYPES = [
    ("test_paper", "试卷", "set", ["卷子", "试卷", "套卷", "模拟卷", "真题卷"], "output_heavy", ["审题", "计算", "书写"], "low"),
    ("exercise_set", "习题/刷题", "problem", ["刷题", "练习题", "习题", "做题"], "practice_heavy", ["计算", "推理"], "medium"),
    ("essay", "作文/写作", "article", ["作文", "写作", "议论文", "记叙文"], "output_heavy", ["构思", "书写", "修改"], "low"),
    ("reading", "阅读", "article", ["阅读", "阅读理解", "读物"], "input_heavy", ["阅读", "理解"], "medium"),
    ("recitation", "背诵", "paragraph", ["背诵", "背课文", "默写"], "memory_heavy", ["记忆", "复述"], "medium"),
    ("vocabulary", "单词/词组", "word", ["单词", "词汇", "背单词", "词组"], "memory_heavy", ["记忆"], "high"),
    ("mistake_review", "错题整理", "problem", ["错题", "订正", "错题本"], "review_heavy", ["分析", "订正"], "medium"),
    ("chapter_review", "章节复习", "chapter", ["复习", "章节", "知识点"], "review_heavy", ["梳理", "记忆"], "low"),
    ("preview", "预习", "page", ["预习", "课前"], "input_light", ["阅读", "标记"], "high"),
    ("lab_report", "实验报告", "report", ["实验报告", "实验"], "output_heavy", ["记录", "分析", "书写"], "low"),
    ("group_work", "小组作业", "deliverable", ["小组作业", "合作"], "collaborative", ["讨论", "分工"], "medium"),
    ("presentation", "展示/PPT", "slide", ["PPT", "展示", "演讲"], "output_heavy", ["制作", "演练"], "low"),
]

SUBJECTS = [
    ("math", "数学", "high_calculation", "high", False, 1.05),
    ("english", "英语", "language_output", "medium", True, 1.0),
    ("chinese", "语文", "language_output", "medium", True, 1.08),
    ("physics", "物理", "high_calculation", "high", False, 1.06),
    ("chemistry", "化学", "mixed_calculation", "medium", False, 1.04),
    ("biology", "生物", "memory_mixed", "medium", True, 1.02),
    ("history", "历史", "memory_heavy", "low", True, 1.0),
    ("politics", "政治", "memory_heavy", "low", True, 1.0),
    ("geography", "地理", "memory_mixed", "low", True, 1.0),
    ("general", "综合/其他", "general", "medium", True, 1.0),
]

# Base minutes per unit (average student, before P_TYPE multiplier in backend)
UNIT_RATE_BASE: dict[tuple[str, str, str], dict] = {
    ("math", "test_paper", "set"): {"p25": 72, "p50": 89, "p75": 110, "setup": 8, "fatigue": 1.10},
    ("math", "test_paper", "page"): {"p25": 28, "p50": 35, "p75": 45, "setup": 5, "fatigue": 1.05},
    ("math", "exercise_set", "problem"): {"p25": 2.2, "p50": 2.8, "p75": 3.5, "setup": 5, "fatigue": 1.03},
    ("math", "mistake_review", "problem"): {"p25": 2.5, "p50": 3.2, "p75": 4.0, "setup": 5, "fatigue": 1.02},
    ("math", "chapter_review", "chapter"): {"p25": 55, "p50": 68, "p75": 85, "setup": 8, "fatigue": 1.05},
    ("english", "essay", "article"): {"p25": 32, "p50": 40, "p75": 52, "setup": 6, "fatigue": 1.08},
    ("english", "vocabulary", "word"): {"p25": 0.32, "p50": 0.40, "p75": 0.52, "setup": 5, "fatigue": 1.02},
    ("english", "reading", "article"): {"p25": 12, "p50": 15, "p75": 20, "setup": 3, "fatigue": 1.04},
    ("english", "recitation", "paragraph"): {"p25": 14, "p50": 18, "p75": 25, "setup": 3, "fatigue": 1.03},
    ("chinese", "essay", "article"): {"p25": 38, "p50": 48, "p75": 62, "setup": 6, "fatigue": 1.08},
    ("chinese", "reading", "article"): {"p25": 14, "p50": 18, "p75": 24, "setup": 3, "fatigue": 1.04},
    ("chinese", "recitation", "paragraph"): {"p25": 16, "p50": 22, "p75": 30, "setup": 3, "fatigue": 1.03},
    ("physics", "exercise_set", "problem"): {"p25": 3.0, "p50": 4.0, "p75": 5.5, "setup": 5, "fatigue": 1.04},
    ("physics", "test_paper", "set"): {"p25": 75, "p50": 92, "p75": 115, "setup": 8, "fatigue": 1.10},
    ("physics", "lab_report", "report"): {"p25": 55, "p50": 70, "p75": 90, "setup": 10, "fatigue": 1.05},
    ("physics", "chapter_review", "chapter"): {"p25": 50, "p50": 65, "p75": 80, "setup": 8, "fatigue": 1.05},
    ("chemistry", "exercise_set", "problem"): {"p25": 2.5, "p50": 3.2, "p75": 4.2, "setup": 5, "fatigue": 1.03},
    ("chemistry", "mistake_review", "problem"): {"p25": 2.8, "p50": 3.5, "p75": 4.5, "setup": 5, "fatigue": 1.02},
    ("chemistry", "lab_report", "report"): {"p25": 50, "p50": 65, "p75": 85, "setup": 10, "fatigue": 1.05},
    ("biology", "exercise_set", "problem"): {"p25": 2.0, "p50": 2.6, "p75": 3.4, "setup": 5, "fatigue": 1.03},
    ("biology", "recitation", "paragraph"): {"p25": 12, "p50": 16, "p75": 22, "setup": 3, "fatigue": 1.03},
    ("biology", "chapter_review", "chapter"): {"p25": 45, "p50": 58, "p75": 72, "setup": 8, "fatigue": 1.05},
    ("history", "reading", "page"): {"p25": 4, "p50": 5, "p75": 7, "setup": 3, "fatigue": 1.02},
    ("history", "chapter_review", "chapter"): {"p25": 40, "p50": 52, "p75": 65, "setup": 6, "fatigue": 1.04},
    ("history", "recitation", "paragraph"): {"p25": 10, "p50": 14, "p75": 20, "setup": 3, "fatigue": 1.03},
    ("politics", "reading", "page"): {"p25": 4, "p50": 5.5, "p75": 7, "setup": 3, "fatigue": 1.02},
    ("politics", "chapter_review", "chapter"): {"p25": 38, "p50": 50, "p75": 62, "setup": 6, "fatigue": 1.04},
    ("politics", "recitation", "paragraph"): {"p25": 10, "p50": 14, "p75": 20, "setup": 3, "fatigue": 1.03},
    ("geography", "exercise_set", "problem"): {"p25": 1.8, "p50": 2.4, "p75": 3.2, "setup": 4, "fatigue": 1.02},
    ("geography", "reading", "page"): {"p25": 4, "p50": 5, "p75": 7, "setup": 3, "fatigue": 1.02},
    ("geography", "chapter_review", "chapter"): {"p25": 38, "p50": 48, "p75": 60, "setup": 6, "fatigue": 1.04},
    ("general", "mistake_review", "problem"): {"p25": 2.5, "p50": 3.2, "p75": 4.0, "setup": 5, "fatigue": 1.02},
    ("general", "group_work", "deliverable"): {"p25": 45, "p50": 60, "p75": 80, "setup": 10, "fatigue": 1.06},
    ("general", "presentation", "slide"): {"p25": 4, "p50": 5.5, "p75": 7, "setup": 8, "fatigue": 1.04},
    ("general", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5.5, "setup": 3, "fatigue": 1.02},
    ("math", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5, "setup": 3, "fatigue": 1.02},
    ("english", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5.5, "setup": 3, "fatigue": 1.02},
    ("chinese", "preview", "page"): {"p25": 3.5, "p50": 4.5, "p75": 6, "setup": 3, "fatigue": 1.02},
    ("physics", "preview", "page"): {"p25": 3.5, "p50": 4.5, "p75": 6, "setup": 3, "fatigue": 1.02},
    ("chemistry", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5.5, "setup": 3, "fatigue": 1.02},
    ("biology", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5, "setup": 3, "fatigue": 1.02},
    ("history", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5, "setup": 3, "fatigue": 1.02},
    ("politics", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5, "setup": 3, "fatigue": 1.02},
    ("geography", "preview", "page"): {"p25": 3, "p50": 4, "p75": 5, "setup": 3, "fatigue": 1.02},
}

SUBJECT_TASK_KEYWORDS: dict[tuple[str, str], list[str]] = {
    ("math", "test_paper"): ["数学卷", "数学试卷", "数学模拟", "数学套卷"],
    ("math", "exercise_set"): ["数学题", "数学刷题", "数学练习"],
    ("math", "mistake_review"): ["数学错题", "数学订正"],
    ("math", "chapter_review"): ["数学复习", "数学章节"],
    ("english", "essay"): ["英语作文", "英语写作"],
    ("english", "vocabulary"): ["英语单词", "背单词", "词汇"],
    ("english", "reading"): ["英语阅读", "英语阅读理解"],
    ("english", "recitation"): ["英语背诵", "背课文"],
    ("chinese", "essay"): ["语文作文", "作文"],
    ("chinese", "reading"): ["语文阅读", "阅读理解"],
    ("chinese", "recitation"): ["语文背诵", "古诗文"],
    ("physics", "exercise_set"): ["物理题", "物理刷题"],
    ("physics", "test_paper"): ["物理卷", "物理试卷"],
    ("physics", "lab_report"): ["物理实验报告"],
    ("chemistry", "exercise_set"): ["化学题", "化学刷题"],
    ("chemistry", "mistake_review"): ["化学错题"],
    ("chemistry", "lab_report"): ["化学实验报告"],
    ("biology", "exercise_set"): ["生物题", "生物练习"],
    ("biology", "chapter_review"): ["生物复习"],
    ("history", "chapter_review"): ["历史复习", "历史章节"],
    ("history", "reading"): ["历史阅读"],
    ("politics", "chapter_review"): ["政治复习"],
    ("politics", "recitation"): ["政治背诵"],
    ("geography", "exercise_set"): ["地理题", "地理选择题"],
    ("geography", "chapter_review"): ["地理复习"],
    ("general", "mistake_review"): ["错题整理", "错题本"],
    ("general", "group_work"): ["小组作业"],
    ("general", "presentation"): ["PPT", "展示"],
}

PLANNING_RULES = [
    ("rule_cognitive_load_daily_cap", "daily_load_cap", {"cognitive_load": "high"}, "同一天 high 负荷任务累计不超过 90 分钟", "P人学生连续高强度任务完成率显著下降"),
    ("rule_essay_pairing", "pairing_forbidden", {"task_type": "essay"}, "同一天避免安排 2 篇以上作文", "写作任务叠加会导致质量下降和拖延"),
    ("rule_vocab_fragmented", "split_strategy", {"task_type": "vocabulary"}, "背单词任务优先拆成 20-25 分钟小段", "记忆类任务适合碎片时间"),
    ("rule_test_paper_continuous", "split_strategy", {"task_type": "test_paper"}, "试卷任务单次连续不超过 45 分钟", "限时训练需要专注但不宜过长"),
    ("rule_chapter_review_weekend", "preferred_block", {"task_type": "chapter_review"}, "章节复习优先安排在周末整块时间", "章节复习需要较长连续时间"),
    ("rule_mistake_review_evening", "preferred_block", {"task_type": "mistake_review"}, "错题整理适合晚间或碎片时段", "错题订正不宜与高难度新题同日"),
    ("rule_lab_report_block", "split_strategy", {"task_type": "lab_report"}, "实验报告拆成「数据整理」和「撰写」两段", "报告类任务分阶段完成更现实"),
    ("rule_reading_continuous", "split_strategy", {"task_type": "reading"}, "阅读任务避免频繁打断", "阅读理解需要上下文连贯"),
    ("rule_preview_light", "daily_load_cap", {"task_type": "preview"}, "预习任务可安排在精力低谷时段", "预习负荷较低"),
    ("rule_group_work_buffer", "ddl_pressure", {"task_type": "group_work"}, "小组作业预留至少 1 天缓冲", "协作任务常有沟通延迟"),
    ("rule_presentation_rehearse", "split_strategy", {"task_type": "presentation"}, "PPT 制作与演练分开安排", "展示类任务需要演练时间"),
    ("rule_exercise_fatigue", "pairing_recommended", {"task_type": "exercise_set"}, "刷题后可搭配轻度复习或错题", "避免连续大量刷题"),
    ("rule_recitation_morning", "preferred_block", {"task_type": "recitation"}, "背诵任务优先早晨或睡前", "记忆类任务有时段偏好"),
    ("rule_multi_set_rest", "split_strategy", {"task_type": "test_paper"}, "每完成 1 套试卷休息至少 10 分钟", "连续套卷需要恢复注意力"),
    ("rule_ddl_tight_p75", "ddl_pressure", {"urgency": "tight"}, "截止紧迫时使用 p75 估时", "时间紧张时应偏保守"),
    ("rule_three_task_cap", "daily_load_cap", {"task_count": 3}, "同一天核心任务不超过 3 项", "P人学生任务过多容易放弃"),
    ("rule_physics_math_separate", "pairing_forbidden", {"subjects": ["physics", "math"]}, "同一天避免数学+物理高强度计算叠加", "双理科高计算量容易疲劳"),
    ("rule_english_vocab_essay", "pairing_forbidden", {"task_types": ["vocabulary", "essay"]}, "同一天避免背单词+写作文叠加", "两类英语输出/记忆任务冲突"),
    ("rule_break_after_60", "split_strategy", {"duration_gte": 60}, "单次学习块超过 60 分钟必须插入休息", "专注力维持上限"),
    ("rule_weekend_bulk", "preferred_block", {"workload_gte": 120}, "总工时超过 120 分钟优先利用周末", "大任务需要整块时间"),
]

DIFFICULTY_MODS = {"easy": 0.80, "medium": 1.00, "hard": 1.25}
GRADE_MODS = {"middle_high": 0.88, "senior_high": 1.00, "exam_sprint": 1.12}


def build_ontology() -> list[dict]:
    records = []
    qty_patterns = {
        "set": ["(\\d+)张", "(\\d+)套"],
        "problem": ["(\\d+)道", "(\\d+)题"],
        "page": ["(\\d+)页"],
        "article": ["(\\d+)篇"],
        "word": ["(\\d+)个", "(\\d+)词"],
        "chapter": ["(\\d+)章", "(\\d+)节"],
        "paragraph": ["(\\d+)段"],
        "report": ["(\\d+)份"],
        "slide": ["(\\d+)页"],
        "deliverable": ["(\\d+)项"],
    }
    for task_type, label, default_unit, aliases, nature, skills, interrupt in TASK_TYPES:
        records.append({
            "record_type": "ontology",
            "id": f"ontology_task_{task_type}",
            "task_type": task_type,
            "task_type_label": label,
            "aliases": aliases,
            "default_work_unit": default_unit,
            "quantity_patterns": qty_patterns.get(default_unit, ["(\\d+)"]),
            "activity_nature": nature,
            "primary_skills": skills,
            "interruptibility": interrupt,
        })
    return records


def build_subject_profiles() -> list[dict]:
    return [
        {
            "record_type": "subject_profile",
            "id": f"subject_profile_{code}",
            "subject": code,
            "subject_label": label,
            "cognitive_style": style,
            "error_recovery_cost": recovery,
            "fragmented_viable": fragmented,
            "p_type_slow_multiplier": mult,
        }
        for code, label, style, recovery, fragmented, mult in SUBJECTS
    ]


def build_unit_rates() -> list[dict]:
    records = []
    for (subject, task_type, work_unit), base in UNIT_RATE_BASE.items():
        records.append({
            "record_type": "unit_rate",
            "id": f"rate_{subject}_{task_type}_{work_unit}",
            "subject": subject,
            "task_type": task_type,
            "work_unit": work_unit,
            "minutes_per_unit_p25": round(base["p25"], 2),
            "minutes_per_unit_p50": round(base["p50"], 2),
            "minutes_per_unit_p75": round(base["p75"], 2),
            "setup_minutes": base["setup"],
            "fatigue_per_extra_unit": base["fatigue"],
            "difficulty_modifiers": DIFFICULTY_MODS,
            "grade_modifiers": GRADE_MODS,
            "evidence_note": "普通学生速率；后端乘 P_TYPE_SLOW_MULTIPLIER 与学科系数",
        })
    return records


def build_task_templates(unit_rates: list[dict]) -> list[dict]:
    rate_ids = {f"rate_{r['subject']}_{r['task_type']}_{r['work_unit']}": r for r in unit_rates}
    records = []
    seen = set()
    for (subject, task_type, work_unit), _ in UNIT_RATE_BASE.items():
        key = (subject, task_type)
        if key in seen:
            continue
        seen.add(key)
        rate_ref = f"rate_{subject}_{task_type}_{work_unit}"
        if rate_ref not in rate_ids:
            continue
        rate = rate_ids[rate_ref]
        keywords = SUBJECT_TASK_KEYWORDS.get(key, [])
        if not keywords:
            subj_label = next(s[1] for s in SUBJECTS if s[0] == subject)
            type_label = next(t[1] for t in TASK_TYPES if t[0] == task_type)
            keywords = [f"{subj_label}{type_label}"]
        default_unit = rate["work_unit"]
        comp = []
        if task_type == "test_paper":
            comp = [
                {"component": "choice_fill", "share": 0.35, "cognitive_load": "medium"},
                {"component": "solution", "share": 0.65, "cognitive_load": "high"},
            ]
        elif task_type == "essay":
            comp = [
                {"component": "outline", "share": 0.15, "cognitive_load": "medium"},
                {"component": "draft", "share": 0.65, "cognitive_load": "high"},
                {"component": "revise", "share": 0.20, "cognitive_load": "medium"},
            ]
        elif task_type == "vocabulary":
            comp = [
                {"component": "learn", "share": 0.60, "cognitive_load": "medium"},
                {"component": "review", "share": 0.40, "cognitive_load": "low"},
            ]
        elif task_type == "lab_report":
            comp = [
                {"component": "data", "share": 0.35, "cognitive_load": "medium"},
                {"component": "write", "share": 0.65, "cognitive_load": "high"},
            ]
        elif task_type == "chapter_review":
            comp = [
                {"component": "notes", "share": 0.50, "cognitive_load": "medium"},
                {"component": "practice", "share": 0.50, "cognitive_load": "medium"},
            ]
        decomp = []
        if task_type == "test_paper":
            decomp = [
                {"when_unit_count_gte": 1, "strategy": "by_set", "chunk_label": "完成第{n}套选择题+填空", "share": 0.35},
                {"when_unit_count_gte": 1, "strategy": "by_set", "chunk_label": "完成第{n}套解答题", "share": 0.65},
            ]
        elif task_type == "essay":
            decomp = [
                {"when_unit_count_gte": 1, "strategy": "by_article", "chunk_label": "第{n}篇：列提纲", "share": 0.15},
                {"when_unit_count_gte": 1, "strategy": "by_article", "chunk_label": "第{n}篇：写作", "share": 0.65},
                {"when_unit_count_gte": 1, "strategy": "by_article", "chunk_label": "第{n}篇：修改", "share": 0.20},
            ]
        elif task_type == "vocabulary":
            decomp = [
                {"when_unit_count_gte": 50, "strategy": "by_chunk", "chunk_label": "背诵单词第{n}批（约50个）", "share": 0.25},
            ]
        elif task_type == "exercise_set":
            decomp = [
                {"when_unit_count_gte": 10, "strategy": "by_chunk", "chunk_label": "完成第{n}组习题（约10道）", "share": 0.5},
            ]
        elif task_type == "mistake_review":
            decomp = [
                {"when_unit_count_gte": 5, "strategy": "by_chunk", "chunk_label": "订正第{n}批错题（约5道）", "share": 0.5},
            ]
        constraints = {
            "max_continuous_minutes": 45 if task_type in ("test_paper", "essay", "chapter_review") else 30,
            "min_gap_minutes": 10,
            "avoid_same_day_types": ["essay", "chapter_review"] if task_type != "preview" else [],
            "preferred_time_blocks": ["evening", "weekend"] if task_type in ("test_paper", "chapter_review", "lab_report") else ["morning", "fragmented"] if task_type == "vocabulary" else ["afternoon", "evening"],
        }
        records.append({
            "record_type": "task_template",
            "id": f"tpl_{subject}_{task_type}_standard",
            "subject": subject,
            "task_type": task_type,
            "match_keywords": keywords,
            "default_unit": default_unit,
            "rate_ref": rate_ref,
            "composition": comp,
            "decomposition_rules": decomp,
            "planning_constraints": constraints,
        })
    return records


def build_planning_rules() -> list[dict]:
    return [
        {
            "record_type": "planning_rule",
            "id": rid,
            "rule_type": rtype,
            "applies_to": applies,
            "constraint": constraint,
            "rationale": rationale,
        }
        for rid, rtype, applies, constraint, rationale in PLANNING_RULES
    ]


def build_calibration_from_old(templates: list[dict]) -> list[dict]:
    tpl_index = {(t["subject"], t["task_type"]): t["id"] for t in templates}
    records = []
    if not OLD.exists():
        return records
    for line in OLD.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            old = json.loads(line)
        except json.JSONDecodeError:
            continue
        subject = old.get("subject", "general")
        task_type = old.get("task_type", "exercise_set")
        p50 = int(old.get("estimated_minutes_p50", 0) or 0)
        pmin = int(old.get("estimated_minutes_min", 0) or 0)
        pmax = int(old.get("estimated_minutes_max", 0) or 0)
        if p50 <= 0:
            continue
        observed = round(p50 * P_TYPE)
        obs_min = round(pmin * P_TYPE) if pmin else round(observed * 0.85)
        obs_max = round(pmax * P_TYPE) if pmax else round(observed * 1.15)
        unit_count = int(old.get("unit_count", 1) or 1)
        records.append({
            "record_type": "calibration_case",
            "id": f"case_{old.get('id', len(records))}",
            "subject": subject,
            "task_type": task_type,
            "work_unit": old.get("work_unit", "item"),
            "unit_count": unit_count,
            "difficulty": old.get("difficulty", "medium"),
            "grade_band": old.get("grade_band", "senior_high"),
            "observed_minutes": observed,
            "observed_range": [obs_min, obs_max],
            "student_profile": "p_type_average",
            "task_description": old.get("description", ""),
            "deviation_factors": ["由 v1 知识库迁移", "已乘 P 人系数 1.18"],
            "source_type": old.get("source_type", "general_estimate"),
            "confidence": float(old.get("confidence", 0.65) or 0.65),
            "template_ref": tpl_index.get((subject, task_type), f"tpl_{subject}_{task_type}_standard"),
        })
    return records


def main() -> None:
    ontology = build_ontology()
    profiles = build_subject_profiles()
    rates = build_unit_rates()
    templates = build_task_templates(rates)
    rules = build_planning_rules()
    calibrations = build_calibration_from_old(templates)
    all_records = ontology + profiles + rates + templates + rules + calibrations
    with OUT.open("w", encoding="utf-8") as fp:
        for rec in all_records:
            fp.write(json.dumps(rec, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for rec in all_records:
        counts[rec["record_type"]] = counts.get(rec["record_type"], 0) + 1
    print(f"Wrote {len(all_records)} records to {OUT}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
