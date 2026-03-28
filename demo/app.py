import streamlit as st

from core.config import (
    APP_TITLE,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
    OLLAMA_NUM_THREAD,
    OLLAMA_MODEL,
    OLLAMA_RETRY_COUNT,
    OLLAMA_TIMEOUT_SECONDS,
    OLLAMA_URL,
    PLAN_MAX_DAYS,
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


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    inject_styles()

    if "started" not in st.session_state:
        st.session_state.started = False
    if "last_plan" not in st.session_state:
        st.session_state.last_plan = None
    if "last_error" not in st.session_state:
        st.session_state.last_error = None

    client = OllamaClient(
        base_url=OLLAMA_URL,
        model=OLLAMA_MODEL,
        timeout_seconds=OLLAMA_TIMEOUT_SECONDS,
        retry_count=OLLAMA_RETRY_COUNT,
        num_predict=OLLAMA_NUM_PREDICT,
        num_ctx=OLLAMA_NUM_CTX,
        num_thread=OLLAMA_NUM_THREAD,
    )
    planner = PlannerService(client, max_days=PLAN_MAX_DAYS)

    render_intro_panel(APP_TITLE)
    started_clicked, _ = render_topbar(APP_TITLE, client.health())
    if started_clicked:
        st.session_state.started = True

    left, middle, right = st.columns([1, 0.04, 1])

    with left:
        with st.container(border=True):
            if not st.session_state.started:
                st.info("点击上方“开始制定计划”后，在左侧填写任务与空闲时段。")
            else:
                tasks = render_task_form()
                availability = render_availability_form()

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
                        with st.spinner("正在连接本地 Ollama 生成计划..."):
                            try:
                                st.session_state.last_plan = planner.generate_daily_plan(valid_tasks, valid_slots)
                                st.session_state.last_error = None
                            except Exception as exc:
                                st.session_state.last_plan = None
                                st.session_state.last_error = str(exc)

    with middle:
        render_split_deco()

    with right:
        with st.container(border=True):
            render_result_panel(st.session_state.last_plan, st.session_state.last_error)


if __name__ == "__main__":
    main()
