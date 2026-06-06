#!/usr/bin/env python3
"""Quick smoke test for RAG v2 parametric estimates."""

import json
from pathlib import Path

from knowledge_rag import build_evidence_package, index_knowledge_by_type

KNOWLEDGE = Path(__file__).resolve().parent / "data" / "knowledge" / "task_knowledge_v2.jsonl"

SAMPLES = [
    {"id": "t1", "title": "数学卷3张", "subject": "math", "taskType": "test_paper", "difficulty": "medium"},
    {"id": "t2", "title": "英语作文2篇", "subject": "english", "taskType": "essay", "difficulty": "medium"},
    {"id": "t3", "title": "背英语单词200个", "subject": "english", "taskType": "vocabulary", "difficulty": "medium"},
]


def main() -> None:
    records = []
    for line in KNOWLEDGE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    indexed = index_knowledge_by_type(records)
    for task in SAMPLES:
        pkg = build_evidence_package(task, indexed, p_type_mult=1.18, estimate_percentile="p50")
        param = pkg["parametric_estimate"]
        print(f"\n=== {task['title']} ===")
        print(f"  unit_count: {pkg['structured_intent']['unit_count']}")
        print(f"  template: {pkg['matched_template_id']}")
        print(f"  p25/p50/p75: {param['p25']}/{param['p50']}/{param['p75']} min")
        print(f"  decomposition: {len(pkg['decomposition_suggestion'])} chunks")
        if pkg["warnings"]:
            print(f"  warnings: {pkg['warnings']}")


if __name__ == "__main__":
    main()
