from datetime import date
from typing import List

import streamlit as st

from core.config import WEEKDAY_LABELS, WEEKDAYS
from core.schemas import AvailabilityInput, TaskInput


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: radial-gradient(circle at top left, #f4f9f7 0%, #f7f8fc 42%, #f9fafb 100%);
            color: #1f2937;
        }
        .main .block-container {
            padding-top: 1.2rem;
            padding-bottom: 1.4rem;
            max-width: 1220px;
        }
        .hero-title {
            font-size: 1.85rem;
            font-weight: 700;
            margin: 0;
            color: #111827;
        }
        .hero-subtitle {
            color: #4b5563;
            font-size: 0.95rem;
            margin-top: 0.3rem;
        }
        .hero-wrap {
            border-radius: 14px;
            border: 1px solid #d9e0ea;
            background: linear-gradient(120deg, #ffffff 0%, #f3f8ff 100%);
            padding: 1rem 1.1rem;
            margin-bottom: 0.85rem;
        }
        .topbar {
            padding: 0.75rem 0 0.2rem 0;
            margin-bottom: 0.9rem;
        }
        .section-title {
            font-size: 1.02rem;
            font-weight: 700;
            margin: 0 0 0.15rem 0;
            color: #1f2937;
        }
        .section-note {
            color: #6b7280;
            font-size: 0.84rem;
            margin-bottom: 0.3rem;
        }
        .small-note {
            color: #6b7280;
            font-size: 0.9rem;
            margin-bottom: 0.6rem;
        }
        .count-badge {
            text-align: center;
            font-size: 1rem;
            font-weight: 700;
            margin-top: 0.12rem;
            color: #111827;
            border: 1px solid #d9e0ea;
            border-radius: 8px;
            padding: 0.08rem 0;
            background: #ffffff;
        }
        .mini-label {
            color: #6b7280;
            font-size: 0.8rem;
            margin-bottom: 0.1rem;
        }
        .task-block {
            padding: 0.05rem 0 0.1rem 0;
        }
        .split-deco {
            margin-top: 0.2rem;
            height: 78vh;
            width: 2px;
            border-radius: 999px;
            background: linear-gradient(180deg, rgba(14, 116, 144, 0.15), rgba(14, 116, 144, 0.45), rgba(14, 116, 144, 0.15));
            margin-left: auto;
            margin-right: auto;
        }
        .subtle-hint {
            font-size: 0.8rem;
            color: #6b7280;
            margin-top: -0.2rem;
            margin-bottom: 0.35rem;
        }
        .panel-title {
            font-size: 1.05rem;
            font-weight: 700;
            color: #111827;
            margin-bottom: 0.35rem;
        }
        .meta-pill {
            display: inline-block;
            padding: 0.24rem 0.6rem;
            border-radius: 999px;
            background: #e8f4fb;
            color: #075985;
            font-size: 0.77rem;
            margin-bottom: 0.45rem;
            border: 1px solid #d0e8f7;
        }
        .day-head {
            font-weight: 700;
            color: #0f172a;
            margin-bottom: 0.35rem;
        }
        .day-meta {
            display: inline-block;
            margin-left: 0.45rem;
            border-radius: 999px;
            border: 1px solid #dbe7f0;
            padding: 0.15rem 0.45rem;
            font-weight: 600;
            font-size: 0.78rem;
            color: #334155;
            background: #f8fafc;
        }
        .result-item {
            border-radius: 10px;
            border: 1px solid #e5e7eb;
            padding: 0.48rem 0.58rem;
            background: #ffffff;
            margin-bottom: 0.35rem;
        }
        .item-task {
            font-weight: 600;
            color: #111827;
            font-size: 0.92rem;
        }
        .item-sub {
            color: #4b5563;
            font-size: 0.86rem;
            margin-top: 0.1rem;
        }
        .info-grid {
            border-radius: 12px;
            border: 1px dashed #ced9e7;
            background: #ffffff;
            padding: 0.68rem 0.82rem;
            margin-bottom: 0.9rem;
        }
        .stButton > button {
            border-radius: 8px;
            border: 1px solid #d1d5db;
            background: #ffffff;
            color: #1f2937;
            min-height: 1.95rem;
            padding: 0.15rem 0.58rem;
            font-weight: 600;
            box-shadow: none;
        }
        .stButton > button:hover {
            border-color: #9ca3af;
            background: #f9fafb;
        }
        .stButton > button[kind="primary"] {
            background: #0f766e;
            color: white;
            border-color: #115e59;
        }
        .stButton > button[kind="primary"]:hover {
            background: #115e59;
            border-color: #134e4a;
        }
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stDateInput"] input,
        div[data-testid="stTimeInput"] input,
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            border-radius: 8px !important;
            border-color: #d1d5db !important;
            background: #ffffff !important;
        }
        div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlockBorderWrapper"] {
            border-radius: 14px;
            border: 1px solid #d8e0ea;
            background: #ffffff;
            box-shadow: 0 6px 24px rgba(15, 23, 42, 0.04);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_intro_panel(title: str) -> None:
    st.markdown(
        f"""
        <div class="hero-wrap">
            <div class="hero-title">{title}</div>
            <div class="hero-subtitle">输入任务与空闲时段，自动生成清晰的每日执行计划，帮助你稳定推进学习任务。</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="info-grid">
            <div><strong>步骤 1：</strong>填写任务（名称、内容、截止日期，可选预计时长）</div>
            <div><strong>步骤 2：</strong>填写你每周可用的学习时段</div>
            <div><strong>步骤 3：</strong>点击“生成按天计划”，在右侧查看拆解结果</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_topbar(title: str, health_msg: str) -> tuple[bool, bool]:
    st.markdown('<div class="topbar">', unsafe_allow_html=True)
    c1, c2 = st.columns([1.05, 1.65])
    with c1:
        start_clicked = st.button("开始制定计划", type="primary", use_container_width=True)
    with c2:
        check_clicked = st.button("检查连接", use_container_width=True)
        if check_clicked:
            st.info(health_msg)
    st.markdown("</div>", unsafe_allow_html=True)
    return start_clicked, check_clicked


def _count_selector(title: str, state_key: str, min_count: int, max_count: int) -> int:
    if state_key not in st.session_state:
        st.session_state[state_key] = min_count

    left, mid, right, tail = st.columns([7, 0.8, 0.8, 1.3])
    with left:
        st.markdown(f'<p class="section-title">{title}</p>', unsafe_allow_html=True)
        st.markdown('<div class="section-note">根据任务量调整数量，保持计划简洁易执行。</div>', unsafe_allow_html=True)
    with mid:
        if st.button("－", key=f"{state_key}_minus"):
            st.session_state[state_key] = max(min_count, st.session_state[state_key] - 1)
    with right:
        if st.button("＋", key=f"{state_key}_plus"):
            st.session_state[state_key] = min(max_count, st.session_state[state_key] + 1)
    with tail:
        st.markdown(
            f'<div class="mini-label">数量</div><div class="count-badge">{st.session_state[state_key]}</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="subtle-hint">可通过 + / - 快速调整</div>', unsafe_allow_html=True)
    return int(st.session_state[state_key])


def render_task_form() -> List[TaskInput]:
    task_count = _count_selector("任务信息", "task_count", 1, 10)

    tasks: List[TaskInput] = []
    for i in range(int(task_count)):
        with st.container(border=False):
            st.markdown('<div class="task-block">', unsafe_allow_html=True)
            st.markdown(f"**任务 {i + 1}**")
            c1, c2 = st.columns([1.2, 2.8])
            with c1:
                name = st.text_input(
                    "任务名称",
                    key=f"task_name_{i}",
                    placeholder="任务名称",
                    label_visibility="collapsed",
                )
            with c2:
                detail = st.text_input(
                    "具体内容",
                    key=f"task_detail_{i}",
                    placeholder="具体内容（如：第3章习题 1-20）",
                    label_visibility="collapsed",
                )

            c3, c4 = st.columns(2)
            with c3:
                est = st.number_input(
                    "预计分钟（可选）",
                    min_value=0,
                    value=0,
                    step=10,
                    key=f"task_est_{i}",
                    label_visibility="collapsed",
                    placeholder="预计分钟（可选）",
                )
            with c4:
                ddl = st.date_input("截止日期", value=date.today(), key=f"task_deadline_{i}", label_visibility="collapsed")

            tasks.append(
                TaskInput(
                    name=name.strip(),
                    detail=detail.strip(),
                    estimated_minutes=int(est) if est > 0 else None,
                    deadline=ddl.strftime("%Y-%m-%d"),
                )
            )
            st.markdown("</div>", unsafe_allow_html=True)
            if i < task_count - 1:
                st.divider()

    return tasks


def render_availability_form() -> List[AvailabilityInput]:
    slot_count = _count_selector("空闲时间段", "slot_count", 1, 14)

    slots: List[AvailabilityInput] = []
    for i in range(int(slot_count)):
        with st.container(border=False):
            st.markdown(f"**时段 {i + 1}**")
            c1, c2, c3 = st.columns([1.2, 1, 1])
            with c1:
                weekday = st.selectbox(
                    "周几",
                    WEEKDAYS,
                    index=i % 7,
                    format_func=lambda d: WEEKDAY_LABELS[d],
                    key=f"slot_week_{i}",
                    label_visibility="collapsed",
                )
            with c2:
                start = st.time_input("开始", key=f"slot_start_{i}", label_visibility="collapsed")
            with c3:
                end = st.time_input("结束", key=f"slot_end_{i}", label_visibility="collapsed")

            slots.append(
                AvailabilityInput(
                    weekday=weekday,
                    start=start.strftime("%H:%M"),
                    end=end.strftime("%H:%M"),
                )
            )
            if i < slot_count - 1:
                st.divider()

    return slots


def render_result_panel(plan: dict | None, error_message: str | None) -> None:
    st.markdown('<div class="panel-title">Ollama 生成结果</div>', unsafe_allow_html=True)
    st.markdown('<div class="meta-pill">结果区将展示按天拆解后的可执行清单</div>', unsafe_allow_html=True)

    if error_message:
        st.error(error_message)

    if not plan:
        st.markdown("<p class='small-note'>结果会显示在这里。提交后将输出按天拆解计划。</p>", unsafe_allow_html=True)
        return

    st.success(f"计划摘要：{plan.get('summary', '-')}")
    risk = plan.get("risk")
    if risk:
        st.warning(f"风险提示：{risk}")

    for day in plan.get("daily_plan", []):
        date_text = day.get("date", "未知日期")
        planned = day.get("planned_minutes", 0)
        available = day.get("total_available_minutes", 0)
        with st.container(border=True):
            st.markdown(
                f'<div class="day-head">{date_text}<span class="day-meta">已规划 {planned} / 可用 {available} 分钟</span></div>',
                unsafe_allow_html=True,
            )
            for item in day.get("items", []):
                slot = item.get("scheduled_slot", "未指定时段")
                task_name = item.get("task_name", "未命名任务")
                step = item.get("step", "步骤")
                minutes = item.get("minutes", 0)
                st.markdown(
                    f"""
                    <div class="result-item">
                        <div class="item-task">[{slot}] {task_name}</div>
                        <div class="item-sub">{step}（{minutes} 分钟）</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    notes = plan.get("notes", [])
    if notes:
        st.markdown("**补充说明**")
        for n in notes:
            st.write(f"- {n}")


def render_split_deco() -> None:
    st.markdown('<div class="split-deco"></div>', unsafe_allow_html=True)

