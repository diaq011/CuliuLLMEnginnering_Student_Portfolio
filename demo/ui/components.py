from datetime import date
from typing import List

import streamlit as st

from core.config import WEEKDAY_LABELS, WEEKDAYS
from core.schemas import AvailabilityInput, TaskInput


def inject_styles(theme: str = "clean_productive_v1") -> None:
    _ = theme
    st.markdown(
        """
        <style>
        :root {
            --bg: #f4f7f2;
            --surface: #ffffff;
            --surface-soft: #f9fbf8;
            --text: #1f2a1f;
            --text-muted: #526152;
            --accent: #1d6b45;
            --accent-strong: #134a2f;
            --warn: #c94f36;
            --border: #d8e4d7;
            --shadow: 0 8px 26px rgba(21, 38, 24, 0.08);
            --radius: 14px;
            --radius-sm: 10px;
        }

        .stApp {
            background:
                radial-gradient(1000px 500px at 15% -10%, #e6f3e9 5%, transparent 65%),
                radial-gradient(900px 460px at 95% 0%, #edf5e8 10%, transparent 68%),
                var(--bg);
            color: var(--text);
        }

        .main .block-container {
            max-width: 1240px;
            padding-top: 0.9rem;
            padding-bottom: 1.1rem;
        }

        .hero {
            border: 1px solid var(--border);
            background: linear-gradient(130deg, #ffffff 0%, #f5fbf5 70%);
            border-radius: var(--radius);
            padding: 1rem 1.1rem;
            box-shadow: var(--shadow);
            margin-bottom: 0.75rem;
        }

        .hero-title {
            margin: 0;
            font-size: 1.7rem;
            font-weight: 800;
            color: #112116;
        }

        .hero-sub {
            margin-top: 0.35rem;
            color: var(--text-muted);
            font-size: 0.94rem;
        }

        .step-row {
            margin-top: 0.7rem;
            display: flex;
            gap: 0.45rem;
            flex-wrap: wrap;
        }

        .step-pill {
            border-radius: 999px;
            border: 1px solid var(--border);
            background: #f7fbf6;
            color: var(--text-muted);
            padding: 0.22rem 0.62rem;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .step-pill.active {
            background: #def3e3;
            border-color: #b8dfc0;
            color: #154e31;
        }

        .panel {
            border: 1px solid var(--border);
            border-radius: var(--radius);
            background: var(--surface);
            box-shadow: var(--shadow);
            padding: 0.85rem 0.95rem;
        }

        .panel-title {
            margin: 0;
            font-size: 1.02rem;
            font-weight: 800;
            color: #152016;
        }

        .panel-note {
            margin-top: 0.2rem;
            color: var(--text-muted);
            font-size: 0.82rem;
        }

        .result-meta {
            display: inline-block;
            margin-right: 0.35rem;
            margin-bottom: 0.35rem;
            border-radius: 999px;
            border: 1px solid #cae2cc;
            background: #ecf7ed;
            color: #1e5d39;
            padding: 0.17rem 0.58rem;
            font-size: 0.77rem;
            font-weight: 600;
        }

        .day-card {
            border: 1px solid #d4e2d4;
            border-radius: var(--radius-sm);
            background: #ffffff;
            padding: 0.62rem 0.7rem;
            margin-bottom: 0.55rem;
        }

        .day-card.today {
            border-color: #74b283;
            box-shadow: 0 0 0 2px rgba(116, 178, 131, 0.16);
        }

        .day-card.overload {
            border-color: #ebc3bc;
            box-shadow: 0 0 0 2px rgba(201, 79, 54, 0.12);
        }

        .day-head {
            font-size: 0.95rem;
            font-weight: 800;
            color: #152016;
            margin-bottom: 0.33rem;
        }

        .day-tag {
            display: inline-block;
            margin-left: 0.42rem;
            border-radius: 999px;
            border: 1px solid #d2e1d2;
            background: #f5faf5;
            padding: 0.1rem 0.45rem;
            font-size: 0.74rem;
            color: #456048;
            font-weight: 700;
        }

        .load-track {
            width: 100%;
            height: 8px;
            background: #edf4ed;
            border-radius: 999px;
            overflow: hidden;
            margin: 0.22rem 0 0.5rem 0;
        }

        .load-fill {
            height: 100%;
            background: linear-gradient(90deg, #56a36c 0%, #2f7f49 100%);
        }

        .load-fill.over {
            background: linear-gradient(90deg, #da735f 0%, #bf4f3a 100%);
        }

        .item {
            border: 1px solid #e2ebe2;
            border-radius: 10px;
            background: #fcfefd;
            padding: 0.4rem 0.52rem;
            margin-bottom: 0.36rem;
        }

        .item-title {
            font-size: 0.89rem;
            font-weight: 700;
            color: #1a2a1d;
        }

        .item-sub {
            margin-top: 0.08rem;
            font-size: 0.82rem;
            color: #4f6050;
        }

        .split-deco {
            margin-top: 0.18rem;
            height: 77vh;
            width: 2px;
            border-radius: 999px;
            background: linear-gradient(180deg, rgba(29, 107, 69, 0.1), rgba(29, 107, 69, 0.45), rgba(29, 107, 69, 0.1));
            margin-left: auto;
            margin-right: auto;
        }

        .stButton > button {
            border-radius: 10px;
            min-height: 2rem;
            font-weight: 700;
            border: 1px solid #c9d9ca;
            background: #fff;
            color: #213022;
        }

        .stButton > button[kind="primary"] {
            background: var(--accent);
            color: #fff;
            border-color: var(--accent-strong);
        }

        .stButton > button[kind="primary"]:hover {
            background: var(--accent-strong);
            border-color: #0f3a24;
        }

        div[data-testid="stNumberInput"] input,
        div[data-testid="stTextInput"] input,
        div[data-testid="stDateInput"] input,
        div[data-testid="stTimeInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            border-radius: 10px !important;
            border-color: #cbdacb !important;
        }

        @media (max-width: 920px) {
            .main .block-container {
                padding-left: 0.75rem;
                padding-right: 0.75rem;
            }
            .split-deco {
                display: none;
            }
            .stButton > button {
                width: 100%;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_intro_panel(title: str, current_step: int) -> None:
    step1 = "active" if current_step >= 1 else ""
    step2 = "active" if current_step >= 2 else ""
    step3 = "active" if current_step >= 3 else ""
    st.markdown(
        f"""
        <div class="hero">
            <h1 class="hero-title">{title}</h1>
            <div class="hero-sub">输入任务与可用时间，系统会先快速排出可执行骨架，再进行智能润色。</div>
            <div class="step-row">
                <span class="step-pill {step1}">1. 任务录入</span>
                <span class="step-pill {step2}">2. 空闲时段</span>
                <span class="step-pill {step3}">3. 生成结果</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(min(1.0, max(0.0, current_step / 3)))


def render_topbar(health_msg: str) -> tuple[bool, bool, bool]:
    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        start_clicked = st.button("开始制定计划", type="primary", use_container_width=True)
    with c2:
        warmup_clicked = st.button("模型预热", use_container_width=True)
    with c3:
        check_clicked = st.button("检查连接", use_container_width=True)

    if check_clicked:
        st.info(health_msg)

    return start_clicked, check_clicked, warmup_clicked


def render_task_form() -> List[TaskInput]:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<p class="panel-title">任务清单</p>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">建议先填 3-6 个重点任务，避免一次输入过多。</div>', unsafe_allow_html=True)

    task_count = int(st.number_input("任务数量", min_value=1, max_value=12, value=3, step=1))
    tasks: List[TaskInput] = []

    for i in range(task_count):
        st.markdown(f"**任务 {i + 1}**")
        c1, c2 = st.columns([1.2, 2.8])
        with c1:
            name = st.text_input("任务名称", key=f"task_name_{i}", placeholder="例如：高数作业")
        with c2:
            detail = st.text_input("任务内容", key=f"task_detail_{i}", placeholder="例如：第 3 章习题 1-20")

        c3, c4 = st.columns(2)
        with c3:
            est = st.number_input(
                "预估时长（分钟，可选）",
                min_value=0,
                value=0,
                step=10,
                key=f"task_est_{i}",
            )
        with c4:
            ddl = st.date_input("截止日期", value=date.today(), key=f"task_deadline_{i}")

        tasks.append(
            TaskInput(
                name=name.strip(),
                detail=detail.strip(),
                estimated_minutes=int(est) if est > 0 else None,
                deadline=ddl.strftime("%Y-%m-%d"),
            )
        )
        if i < task_count - 1:
            st.divider()

    st.markdown("</div>", unsafe_allow_html=True)
    return tasks


def render_availability_form() -> List[AvailabilityInput]:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<p class="panel-title">空闲时段</p>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">填写你固定可学习的时段，排程会严格受此约束。</div>', unsafe_allow_html=True)

    slot_count = int(st.number_input("时段数量", min_value=1, max_value=21, value=5, step=1))
    slots: List[AvailabilityInput] = []

    for i in range(slot_count):
        st.markdown(f"**时段 {i + 1}**")
        c1, c2, c3 = st.columns([1.2, 1, 1])
        with c1:
            weekday = st.selectbox(
                "星期",
                WEEKDAYS,
                index=i % 7,
                format_func=lambda d: WEEKDAY_LABELS[d],
                key=f"slot_week_{i}",
            )
        with c2:
            start = st.time_input("开始", key=f"slot_start_{i}")
        with c3:
            end = st.time_input("结束", key=f"slot_end_{i}")

        slots.append(
            AvailabilityInput(
                weekday=weekday,
                start=start.strftime("%H:%M"),
                end=end.strftime("%H:%M"),
            )
        )
        if i < slot_count - 1:
            st.divider()

    st.markdown("</div>", unsafe_allow_html=True)
    return slots


def render_result_panel(plan: dict | None, error_message: str | None) -> None:
    st.markdown('<div class="panel">', unsafe_allow_html=True)
    st.markdown('<p class="panel-title">按天计划结果</p>', unsafe_allow_html=True)
    st.markdown('<div class="panel-note">右侧会展示按天拆解的执行清单与负载情况。</div>', unsafe_allow_html=True)

    if error_message:
        st.error(error_message)

    if not plan:
        st.info("结果会显示在这里。填写左侧内容后点击“生成按天计划”。")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    meta = plan.get("meta", {}) if isinstance(plan.get("meta", {}), dict) else {}
    mode = str(meta.get("mode", "unknown"))
    elapsed = meta.get("elapsed_ms_total")
    model = meta.get("model", "-")
    fallback_flag = "是" if meta.get("used_fallback") else "否"

    st.markdown(f'<span class="result-meta">模式：{mode}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="result-meta">模型：{model}</span>', unsafe_allow_html=True)
    st.markdown(f'<span class="result-meta">本地兜底：{fallback_flag}</span>', unsafe_allow_html=True)
    if isinstance(elapsed, int):
        st.markdown(f'<span class="result-meta">总耗时：{elapsed} ms</span>', unsafe_allow_html=True)

    summary = plan.get("summary", "")
    if summary:
        st.success(f"计划摘要：{summary}")

    risk = plan.get("risk", "")
    if risk:
        st.warning(f"风险提示：{risk}")

    need_more_info = bool(plan.get("need_more_info", False))
    questions = plan.get("questions", []) if isinstance(plan.get("questions", []), list) else []
    if need_more_info and questions:
        st.info("模型需要你补充以下信息后可给出更稳的计划：")
        for idx, question in enumerate(questions, start=1):
            if isinstance(question, str) and question.strip():
                st.write(f"{idx}. {question.strip()}")

    today_text = date.today().strftime("%Y-%m-%d")

    for day in plan.get("daily_plan", []):
        day_date = str(day.get("date", "未知日期"))
        available = int(day.get("total_available_minutes", 0) or 0)
        planned = int(day.get("planned_minutes", 0) or 0)
        items = day.get("items", []) if isinstance(day.get("items", []), list) else []

        load_ratio = 0 if available <= 0 else int(min(100, (planned / available) * 100))
        overload = planned > available and available > 0
        day_classes = ["day-card"]
        if day_date == today_text:
            day_classes.append("today")
        if overload:
            day_classes.append("overload")

        tag_text = "今日优先" if day_date == today_text else ("超载" if overload else "可执行")
        fill_class = "load-fill over" if overload else "load-fill"

        st.markdown(
            f"""
            <div class="{' '.join(day_classes)}">
                <div class="day-head">{day_date}<span class="day-tag">{tag_text}</span></div>
                <div>已规划 {planned} / 可用 {available} 分钟</div>
                <div class="load-track"><div class="{fill_class}" style="width:{load_ratio}%"></div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        for item in items:
            slot = str(item.get("scheduled_slot", "未指定时段"))
            task_name = str(item.get("task_name", "未命名任务"))
            step = str(item.get("step", "执行该任务"))
            minutes = int(item.get("minutes", 0) or 0)
            st.markdown(
                f"""
                <div class="item">
                    <div class="item-title">[{slot}] {task_name}</div>
                    <div class="item-sub">{step}（{minutes} 分钟）</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    notes = plan.get("notes", []) if isinstance(plan.get("notes", []), list) else []
    if notes:
        st.markdown("**补充说明**")
        for note in notes:
            st.write(f"- {note}")

    st.markdown("</div>", unsafe_allow_html=True)


def render_split_deco() -> None:
    st.markdown('<div class="split-deco"></div>', unsafe_allow_html=True)
