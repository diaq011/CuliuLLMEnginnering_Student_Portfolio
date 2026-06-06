"""RAG v2: parametric task knowledge — parse, match, compute, package."""

from __future__ import annotations

import math
import re
from typing import Any, Callable

ESTIMATE_MIN = 15
ESTIMATE_MAX_TASK = 480

LINEAR_UNITS = frozenset({"word", "problem", "page"})
FATIGUE_BATCH_SIZE: dict[str, int] = {
    "word": 50,
    "problem": 10,
    "page": 3,
}

DEFAULT_UNIT_COUNTS: dict[str, int] = {
    "set": 1,
    "problem": 10,
    "page": 5,
    "article": 1,
    "word": 50,
    "chapter": 1,
    "paragraph": 1,
    "report": 1,
    "slide": 10,
    "deliverable": 1,
    "item": 1,
}

CHINESE_NUMS = {
    "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
}


def clamp_task_minutes(value: int) -> int:
    return max(ESTIMATE_MIN, min(int(value), ESTIMATE_MAX_TASK))


def index_knowledge_by_type(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    indexed: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        rtype = str(rec.get("record_type") or "legacy").strip()
        indexed.setdefault(rtype, []).append(rec)
    return indexed


def parse_chinese_number(text: str) -> int | None:
    if text.isdigit():
        return int(text)
    if text in CHINESE_NUMS:
        return CHINESE_NUMS[text]
    if text.startswith("十"):
        rest = text[1:]
        return 10 + (CHINESE_NUMS.get(rest, 0) if rest else 0)
    if "十" in text:
        parts = text.split("十", 1)
        tens = CHINESE_NUMS.get(parts[0], 1) if parts[0] else 1
        ones = CHINESE_NUMS.get(parts[1], 0) if len(parts) > 1 and parts[1] else 0
        return tens * 10 + ones
    return None


def extract_unit_count(title: str, work_unit: str, patterns: list[str] | None = None) -> int:
    title = str(title or "")
    unit_patterns = patterns or []
    default_patterns = [
        r"(\d+)\s*张", r"(\d+)\s*套", r"(\d+)\s*道", r"(\d+)\s*题",
        r"(\d+)\s*页", r"(\d+)\s*篇", r"(\d+)\s*个", r"(\d+)\s*词",
        r"(\d+)\s*章", r"(\d+)\s*份", r"(\d+)\s*段",
        r"([一二两三四五六七八九十]+)\s*张", r"([一二两三四五六七八九十]+)\s*套",
        r"([一二两三四五六七八九十]+)\s*篇", r"([一二两三四五六七八九十]+)\s*道",
    ]
    all_patterns = unit_patterns + default_patterns
    for pattern in all_patterns:
        m = re.search(pattern, title)
        if not m:
            continue
        raw = m.group(1)
        val = parse_chinese_number(raw) if not raw.isdigit() else int(raw)
        if val and val > 0:
            return val
    return DEFAULT_UNIT_COUNTS.get(work_unit, 1)


def detect_implicit_flags(title: str) -> list[str]:
    flags = []
    checks = [
        ("含订正", ["订正", "批改", "改错"]),
        ("限时", ["限时", "模拟考", "考试模式"]),
        ("背诵不熟", ["不熟", "新词", "第一次背"]),
        ("高质量", ["精修", "润色", "高分"]),
    ]
    for flag, keywords in checks:
        if any(kw in title for kw in keywords):
            flags.append(flag)
    return flags


def parse_task_intent(
    task: dict[str, Any],
    ontology_records: list[dict[str, Any]],
) -> dict[str, Any]:
    subject = task.get("subject", "general")
    task_type = task.get("taskType", "exercise_set")
    difficulty = task.get("difficulty", "medium")
    title = str(task.get("title", ""))

    default_unit = "item"
    quantity_patterns: list[str] = []
    for ont in ontology_records:
        if ont.get("task_type") == task_type:
            default_unit = ont.get("default_work_unit", default_unit)
            quantity_patterns = list(ont.get("quantity_patterns") or [])
            break

    unit_count = extract_unit_count(title, default_unit, quantity_patterns)
    flags = detect_implicit_flags(title)
    if "含订正" in flags:
        unit_count = max(unit_count, 1)

    return {
        "subject": subject,
        "task_type": task_type,
        "difficulty": difficulty,
        "grade_band": task.get("gradeBand", "senior_high"),
        "title": title,
        "work_unit": default_unit,
        "unit_count": unit_count,
        "implicit_flags": flags,
    }


def tokenize_title(text: str) -> set[str]:
    parts = re.findall(r"[A-Za-z0-9\u4e00-\u9fff]+", str(text).lower())
    return set(parts)


def score_template_match(
    intent: dict[str, Any],
    template: dict[str, Any],
    ontology_aliases: list[str],
) -> float:
    title = intent.get("title", "")
    tokens = tokenize_title(title)
    keywords = list(template.get("match_keywords") or []) + ontology_aliases
    kw_hits = sum(1 for kw in keywords if kw and kw in title)
    kw_score = min(1.0, kw_hits / max(1, min(3, len(keywords))))

    searchable = " ".join(keywords)
    rtokens = tokenize_title(searchable)
    union = tokens | rtokens
    text_score = 0.0 if not union else len(tokens & rtokens) / len(union)

    subject_score = 1.0 if template.get("subject") == intent.get("subject") else 0.0
    type_score = 1.0 if template.get("task_type") == intent.get("task_type") else 0.0
    unit_score = 1.0 if template.get("default_unit") == intent.get("work_unit") else 0.5

    return (
        kw_score * 0.30
        + text_score * 0.15
        + subject_score * 0.25
        + type_score * 0.20
        + unit_score * 0.10
    )


def match_task_template(
    intent: dict[str, Any],
    templates: list[dict[str, Any]],
    ontology_records: list[dict[str, Any]],
) -> tuple[dict[str, Any] | None, float]:
    aliases: list[str] = []
    for ont in ontology_records:
        if ont.get("task_type") == intent.get("task_type"):
            aliases = list(ont.get("aliases") or [])
            break

    best: dict[str, Any] | None = None
    best_score = 0.0
    for tpl in templates:
        if tpl.get("subject") != intent.get("subject"):
            continue
        if tpl.get("task_type") != intent.get("task_type"):
            continue
        score = score_template_match(intent, tpl, aliases)
        if score > best_score:
            best_score = score
            best = tpl
    if best is None:
        for tpl in templates:
            if tpl.get("task_type") != intent.get("task_type"):
                continue
            score = score_template_match(intent, tpl, aliases) * 0.7
            if score > best_score:
                best_score = score
                best = tpl
    return best, best_score


def get_rate_record(
    rate_ref: str,
    rates_by_id: dict[str, dict[str, Any]],
    intent: dict[str, Any],
) -> dict[str, Any] | None:
    if rate_ref in rates_by_id:
        return rates_by_id[rate_ref]
    subject = intent.get("subject", "general")
    task_type = intent.get("task_type", "exercise_set")
    work_unit = intent.get("work_unit", "item")
    fallback_id = f"rate_{subject}_{task_type}_{work_unit}"
    return rates_by_id.get(fallback_id)


def compute_unit_total(
    unit_count: int,
    rate: dict[str, Any],
    percentile: str,
    difficulty: str,
    grade_band: str,
    subject_mult: float,
    p_type_mult: float,
) -> tuple[int, int, int, str]:
    pkey = f"minutes_per_unit_{percentile}"
    if percentile not in ("p25", "p50", "p75"):
        percentile = "p50"
        pkey = "minutes_per_unit_p50"

    def per_unit(key: str) -> float:
        return float(rate.get(f"minutes_per_unit_{key}", 0) or 0)

    setup = float(rate.get("setup_minutes", 0) or 0)
    fatigue_base = float(rate.get("fatigue_per_extra_unit", 1.0) or 1.0)
    diff_mod = float((rate.get("difficulty_modifiers") or {}).get(difficulty, 1.0))
    grade_mod = float((rate.get("grade_modifiers") or {}).get(grade_band, 1.0))

    work_unit = str(rate.get("work_unit") or "item")

    def total_for(key: str) -> int:
        per = per_unit(key)
        if per <= 0:
            return 0
        if work_unit in LINEAR_UNITS:
            unit_sum = per * unit_count
            batch_n = max(1, math.ceil(unit_count / FATIGUE_BATCH_SIZE.get(work_unit, unit_count)))
            fatigue_mult = fatigue_base ** max(0, batch_n - 1)
            raw = (setup + unit_sum * fatigue_mult) * diff_mod * grade_mod * subject_mult * p_type_mult
        else:
            unit_sum = 0.0
            for i in range(unit_count):
                fatigue = fatigue_base ** max(0, i)
                unit_sum += per * fatigue
            raw = (setup + unit_sum) * diff_mod * grade_mod * subject_mult * p_type_mult
        return clamp_task_minutes(round(raw))

    p25 = total_for("p25")
    p50 = total_for("p50")
    p75 = total_for("p75")
    formula = (
        f"setup({setup}) + {unit_count}×rate×fatigue({fatigue_base}) "
        f"×diff({diff_mod})×grade({grade_mod})×subj({subject_mult})×P({p_type_mult})"
    )
    pick = {"p25": p25, "p50": p50, "p75": p75}.get(percentile, p50)
    return p25, p50, p75, formula


def apply_decomposition(
    template: dict[str, Any] | None,
    intent: dict[str, Any],
    total_minutes: int,
) -> list[dict[str, Any]]:
    if not template:
        return [{"label": intent.get("title", "任务"), "minutes": total_minutes}]
    rules = list(template.get("decomposition_rules") or [])
    unit_count = int(intent.get("unit_count", 1) or 1)
    suggestions: list[dict[str, Any]] = []
    if not rules:
        chunk = int(template.get("planning_constraints", {}).get("max_continuous_minutes", 45) or 45)
        remain = total_minutes
        idx = 1
        while remain > 0:
            part = min(remain, chunk)
            suggestions.append({"label": f"第{idx}段：{intent.get('title', '任务')}", "minutes": part})
            remain -= part
            idx += 1
        return suggestions

    work_unit = intent.get("work_unit", "item")
    if work_unit == "word" and unit_count > 50:
        batch = FATIGUE_BATCH_SIZE.get("word", 50)
        batches = max(1, math.ceil(unit_count / batch))
        per_batch = max(ESTIMATE_MIN, round(total_minutes / batches))
        for n in range(1, batches + 1):
            start = (n - 1) * batch + 1
            end = min(n * batch, unit_count)
            suggestions.append({
                "label": f"背诵单词第{n}批（{start}-{end}个）",
                "minutes": per_batch,
            })
        return suggestions

    if work_unit == "problem" and unit_count > 10:
        batch = FATIGUE_BATCH_SIZE.get("problem", 10)
        batches = max(1, math.ceil(unit_count / batch))
        per_batch = max(ESTIMATE_MIN, round(total_minutes / batches))
        for n in range(1, batches + 1):
            suggestions.append({
                "label": f"完成第{n}组习题（约{batch}道）",
                "minutes": per_batch,
            })
        return suggestions

    for n in range(1, unit_count + 1):
        for rule in rules:
            threshold = int(rule.get("when_unit_count_gte", 1) or 1)
            if unit_count < threshold and threshold > 1:
                continue
            share = float(rule.get("share", 0.5))
            label = str(rule.get("chunk_label", "子任务")).replace("{n}", str(n))
            minutes = max(ESTIMATE_MIN, round(total_minutes * share / max(1, unit_count)))
            suggestions.append({"label": label, "minutes": minutes})
    if not suggestions:
        suggestions.append({"label": intent.get("title", "任务"), "minutes": total_minutes})
    return suggestions


def retrieve_calibration_cases(
    intent: dict[str, Any],
    cases: list[dict[str, Any]],
    template_id: str | None,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    intent_units = int(intent.get("unit_count", 1) or 1)
    for case in cases:
        if case.get("subject") != intent.get("subject"):
            continue
        if case.get("task_type") != intent.get("task_type"):
            continue
        unit_count = int(case.get("unit_count", 1) or 1)
        unit_dist = abs(unit_count - intent_units) / max(intent_units, unit_count, 1)
        unit_score = max(0.0, 1.0 - unit_dist)
        tpl_score = 1.0 if template_id and case.get("template_ref") == template_id else 0.5
        diff_score = 1.0 if case.get("difficulty") == intent.get("difficulty") else 0.6
        conf = float(case.get("confidence", 0.5) or 0.5)
        score = unit_score * 0.4 + tpl_score * 0.25 + diff_score * 0.2 + conf * 0.15
        scored.append((score, case))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [c for _, c in scored[:top_k]]


def check_calibration_warning(
    p50: int,
    cases: list[dict[str, Any]],
    intent_unit_count: int = 1,
) -> list[str]:
    warnings: list[str] = []
    if not cases or p50 <= 0:
        return warnings
    for case in cases:
        case_units = int(case.get("unit_count", 1) or 1)
        if case_units != intent_unit_count:
            continue
        obs = int(case.get("observed_minutes", 0) or 0)
        if obs <= 0:
            continue
        drift = abs(p50 - obs) / obs
        if drift > 0.30:
            warnings.append(
                f"参数化估时({p50}min)与标定案例{case.get('id')}({obs}min)偏差{round(drift*100)}%"
            )
    return warnings


def retrieve_planning_rules(
    intent: dict[str, Any],
    template: dict[str, Any] | None,
    rules: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matched = []
    task_type = intent.get("task_type")
    for rule in rules:
        applies = rule.get("applies_to") or {}
        if "task_type" in applies and applies["task_type"] == task_type:
            matched.append(rule)
        elif "cognitive_load" in applies and template:
            comp = template.get("composition") or []
            loads = {c.get("cognitive_load") for c in comp if c.get("cognitive_load")}
            if applies["cognitive_load"] in loads:
                matched.append(rule)
    return matched[:5]


def compute_parametric_estimate(
    intent: dict[str, Any],
    template: dict[str, Any] | None,
    rates_by_id: dict[str, dict[str, Any]],
    subject_profiles: dict[str, dict[str, Any]],
    p_type_mult: float,
    estimate_percentile: str,
) -> dict[str, Any]:
    rate_ref = (template or {}).get("rate_ref", "")
    rate = get_rate_record(rate_ref, rates_by_id, intent) if rate_ref else None
    if rate is None:
        fallback_id = f"rate_{intent.get('subject')}_{intent.get('task_type')}_{intent.get('work_unit')}"
        rate = rates_by_id.get(fallback_id)
    if rate is None:
        rate = rates_by_id.get(f"rate_general_mistake_review_problem")

    subject = intent.get("subject", "general")
    subj_prof = subject_profiles.get(subject, {})
    subject_mult = float(subj_prof.get("p_type_slow_multiplier", 1.0) or 1.0)

    unit_count = int(intent.get("unit_count", 1) or 1)
    if "含订正" in intent.get("implicit_flags", []):
        subject_mult *= 1.08

    p25, p50, p75, formula = compute_unit_total(
        unit_count,
        rate or {},
        estimate_percentile,
        intent.get("difficulty", "medium"),
        intent.get("grade_band", "senior_high"),
        subject_mult,
        p_type_mult,
    )
    pick = {"p25": p25, "p50": p50, "p75": p75}.get(estimate_percentile, p50)
    return {
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "picked": pick,
        "formula_breakdown": formula,
        "rate_ref": (rate or {}).get("id"),
        "unit_count": unit_count,
    }


def build_evidence_package(
    task: dict[str, Any],
    indexed: dict[str, list[dict[str, Any]]],
    p_type_mult: float = 1.18,
    estimate_percentile: str = "p50",
    calibration_top_k: int = 3,
) -> dict[str, Any]:
    ontology = indexed.get("ontology", [])
    templates = indexed.get("task_template", [])
    rates = indexed.get("unit_rate", [])
    cases = indexed.get("calibration_case", [])
    rules = indexed.get("planning_rule", [])

    rates_by_id = {r["id"]: r for r in rates if r.get("id")}
    subject_profiles = {p["subject"]: p for p in indexed.get("subject_profile", []) if p.get("subject")}

    intent = parse_task_intent(task, ontology)
    template, match_score = match_task_template(intent, templates, ontology)
    if template:
        intent["work_unit"] = template.get("default_unit", intent.get("work_unit"))

    parametric = compute_parametric_estimate(
        intent, template, rates_by_id, subject_profiles, p_type_mult, estimate_percentile,
    )
    template_id = (template or {}).get("id")
    cal_cases = retrieve_calibration_cases(intent, cases, template_id, calibration_top_k)
    warnings = check_calibration_warning(
        parametric["p50"], cal_cases, int(intent.get("unit_count", 1) or 1),
    )
    decomp = apply_decomposition(template, intent, parametric["picked"])
    planning = retrieve_planning_rules(intent, template, rules)
    if template:
        planning.extend([
            {"rule_type": "template_constraint", "constraint": v, "rationale": k}
            for k, v in (template.get("planning_constraints") or {}).items()
            if isinstance(v, (str, int, float))
        ])

    return {
        "task_id": task.get("id"),
        "structured_intent": intent,
        "matched_template_id": template_id,
        "template_match_score": round(match_score, 4),
        "parametric_estimate": parametric,
        "decomposition_suggestion": decomp,
        "calibration_cases": [
            {
                "id": c.get("id"),
                "observed_minutes": c.get("observed_minutes"),
                "observed_range": c.get("observed_range"),
                "unit_count": c.get("unit_count"),
                "task_description": c.get("task_description"),
                "confidence": c.get("confidence"),
            }
            for c in cal_cases
        ],
        "planning_constraints": planning,
        "warnings": warnings,
    }


def evidence_to_rag_examples(package: dict[str, Any]) -> list[dict[str, Any]]:
    """Backward-compatible rag_examples list for LLM evidence_ids."""
    examples: list[dict[str, Any]] = []
    param = package.get("parametric_estimate") or {}
    picked = int(param.get("picked") or param.get("p50") or 0)
    intent = package.get("structured_intent") or {}

    if package.get("matched_template_id"):
        examples.append({
            "sample_id": package["matched_template_id"],
            "source": "task_template",
            "task_title": intent.get("title", ""),
            "actual_minutes": picked,
            "estimated_minutes": picked,
            "estimated_minutes_min": param.get("p25"),
            "estimated_minutes_max": param.get("p75"),
            "subject": intent.get("subject"),
            "task_type": intent.get("task_type"),
            "difficulty": intent.get("difficulty"),
            "planning_advice": param.get("formula_breakdown", ""),
            "score": float(package.get("template_match_score") or 0.5),
        })
    if param.get("rate_ref"):
        examples.append({
            "sample_id": param["rate_ref"],
            "source": "unit_rate",
            "task_title": f"单位速率 {intent.get('work_unit')}×{intent.get('unit_count')}",
            "actual_minutes": picked,
            "estimated_minutes": picked,
            "estimated_minutes_min": param.get("p25"),
            "estimated_minutes_max": param.get("p75"),
            "subject": intent.get("subject"),
            "task_type": intent.get("task_type"),
            "difficulty": intent.get("difficulty"),
            "score": 0.85,
        })
    for case in package.get("calibration_cases") or []:
        cid = case.get("id")
        if not cid:
            continue
        examples.append({
            "sample_id": cid,
            "source": "calibration_case",
            "task_title": case.get("task_description", ""),
            "actual_minutes": int(case.get("observed_minutes") or 0),
            "estimated_minutes": int(case.get("observed_minutes") or 0),
            "subject": intent.get("subject"),
            "task_type": intent.get("task_type"),
            "difficulty": intent.get("difficulty"),
            "score": float(case.get("confidence") or 0.6),
        })
    return examples


def fallback_estimate_from_package(
    task: dict[str, Any],
    package: dict[str, Any] | None,
    history_examples: list[dict[str, Any]],
    clamp_fn: Callable[[int], int],
) -> tuple[int, str]:
    user_est = int(task.get("estimatedMinutes") or 0)
    if history_examples:
        vals = sorted(int(e.get("actual_minutes") or e.get("estimated_minutes") or 0) for e in history_examples)
        vals = [v for v in vals if v > 0]
        if vals:
            median = vals[len(vals) // 2]
            if user_est > 0:
                mixed = round(user_est * 0.6 + median * 0.4)
                return clamp_fn(mixed), f"用户预估({user_est}) + 历史中位数({median})融合"
            return clamp_fn(median), f"基于历史样本中位数({median})"

    if package:
        param = package.get("parametric_estimate") or {}
        picked = int(param.get("picked") or param.get("p50") or 0)
        if picked > 0:
            if user_est > 0:
                mixed = round(user_est * 0.35 + picked * 0.65)
                return clamp_fn(mixed), f"参数化估时({picked}) + 用户预估({user_est})融合"
            return clamp_fn(picked), f"参数化估时 {picked} 分钟（{param.get('formula_breakdown', '')}）"

    if user_est > 0:
        return clamp_fn(user_est), f"基于用户预估({user_est})，证据不足"
    return clamp_fn(60), "无样本且无用户预估，采用默认 60 分钟"
