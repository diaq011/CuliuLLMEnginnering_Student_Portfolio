import streamlit as st

from core.config import (
    APP_TITLE,
    OLLAMA_FAST_TIMEOUT_SECONDS,
    OLLAMA_MODEL_QUALITY,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_NUM_THREAD,
    OLLAMA_RETRY_COUNT,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
    OLLAMA_MODEL,
    PLAN_MAX_DAYS,
    UI_THEME,
)
from core.schemas import validate_availability, validate_tasks
from services.ollama_client import OllamaClient
from services.planner import PlannerService
from ui.components import (
    inject_styles,
    render_availability_form,
    render_intro_panel,
    render_result_panel,
    render_split_deco,
    render_task_form,
    render_topbar,
)


def _compute_step() -> int:
    if not st.session_state.get("started", False):
        return 1
    if st.session_state.get("last_plan") or st.session_state.get("last_error"):
        return 3
    return 2


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_styles(UI_THEME)

    if "started" not in st.session_state:
        st.session_state.started = False
    if "last_plan" not in st.session_state:
        st.session_state.last_plan = None
    if "last_error" not in st.session_state:
        st.session_state.last_error = None
    if "model_mode" not in st.session_state:
        st.session_state.model_mode = "极速模式（默认）"

    client = OllamaClient(
        base_url=OLLAMA_URL,
        model=OLLAMA_MODEL,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        retry_count=OLLAMA_RETRY_COUNT,
        num_predict=OLLAMA_NUM_PREDICT,
        num_ctx=OLLAMA_NUM_CTX,
        num_thread=OLLAMA_NUM_THREAD,
    )
    planner = PlannerService(
        client,
        max_days=PLAN_MAX_DAYS,
        quality_model=OLLAMA_MODEL_QUALITY,
        fast_timeout_seconds=OLLAMA_FAST_TIMEOUT_SECONDS,
    )

    render_intro_panel(APP_TITLE, _compute_step())
    started_clicked, _, warmup_clicked = render_topbar(client.health())

    if started_clicked:
        st.session_state.started = True

    if warmup_clicked:
        warm_model = OLLAMA_MODEL_QUALITY if st.session_state.model_mode.startswith("质量") else OLLAMA_MODEL
        warm_result = client.warmup(model=warm_model, timeout_seconds=OLLAMA_FAST_TIMEOUT_SECONDS)
        if warm_result.get("ok"):
            st.success(f"预热完成：{warm_result.get('model')}（{warm_result.get('elapsed_ms')} ms）")
        else:
            st.warning(f"预热失败：{warm_result.get('error', 'unknown error')}")

    left, middle, right = st.columns([1, 0.04, 1])

    with left:
        if not st.session_state.started:
            st.info("点击上方“开始制定计划”后，在左侧填写任务与空闲时段。")
        else:
            tasks = render_task_form()
            availability = render_availability_form()

            st.session_state.model_mode = st.radio(
                "推理模式",
                ["极速模式（默认）", "质量模式（更稳）"],
                horizontal=True,
                index=0 if st.session_state.model_mode.startswith("极速") else 1,
                help="极速模式优先响应速度；质量模式采用更谨慎的润色策略。",
            )
            planner.set_prefer_quality(st.session_state.model_mode.startswith("质量"))

            if st.button("生成按天计划", type="primary", use_container_width=True):
                valid_tasks = validate_tasks(tasks)
                valid_slots = validate_availability(availability)

                if not valid_tasks:
                    st.session_state.last_error = "请至少填写 1 个有效任务（任务名称 + 截止日期）。"
                    st.session_state.last_plan = None
                elif not valid_slots:
                    st.session_state.last_error = "请至少填写 1 条有效空闲时段（开始时间需早于结束时间）。"
                    st.session_state.last_plan = None
                else:
                    with st.spinner("正在生成计划（先快速排程，再进行智能润色）..."):
                        try:
                            st.session_state.last_plan = planner.generate_daily_plan(valid_tasks, valid_slots)
                            st.session_state.last_error = None
                        except Exception as exc:
                            st.session_state.last_plan = None
                            st.session_state.last_error = str(exc)

    with middle:
        render_split_deco()

    with right:
        render_result_panel(st.session_state.last_plan, st.session_state.last_error)


if __name__ == "__main__":
    main()
