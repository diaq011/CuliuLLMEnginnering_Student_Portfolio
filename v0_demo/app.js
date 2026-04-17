const API_BASE = window.location.origin.startsWith("http")
  ? `${window.location.origin}/api`
  : "http://127.0.0.1:5000/api";

const state = {
  tasks: [],
  todayPlan: null,
  checkins: [],
  planner: "none",
  activePage: "home",
  timerSeconds: 0,
  timerRunning: false,
  timerHandle: null,
};

const ui = {
  pages: Array.from(document.querySelectorAll(".page")),
  navItems: Array.from(document.querySelectorAll(".nav-item")),
  timerDisplay: document.getElementById("timerDisplay"),
  timerToggleBtn: document.getElementById("timerToggleBtn"),
  timerResetBtn: document.getElementById("timerResetBtn"),
  taskForm: document.getElementById("taskForm"),
  titleInput: document.getElementById("titleInput"),
  deadlineInput: document.getElementById("deadlineInput"),
  estimateInput: document.getElementById("estimateInput"),
  generateBtn: document.getElementById("generateBtn"),
  generateSpinner: document.getElementById("generateSpinner"),
  timelineHeader: document.getElementById("timelineHeader"),
  timelineCanvas: document.getElementById("timelineCanvas"),
  planList: document.getElementById("planList"),
  feedbackBox: document.getElementById("feedbackBox"),
};

bootstrap().catch((error) => {
  setFeedback(`初始化失败：${error.message}`, true);
});

ui.navItems.forEach((item) => {
  item.addEventListener("click", () => {
    const target = item.dataset.nav;
    switchPage(target);
  });
});

ui.timerToggleBtn.addEventListener("click", () => {
  state.timerRunning = !state.timerRunning;
  ui.timerToggleBtn.textContent = state.timerRunning ? "暂停" : "开始";
  if (state.timerRunning) {
    state.timerHandle = setInterval(() => {
      state.timerSeconds += 1;
      renderTimer();
    }, 1000);
  } else if (state.timerHandle) {
    clearInterval(state.timerHandle);
    state.timerHandle = null;
  }
});

ui.timerResetBtn.addEventListener("click", () => {
  state.timerSeconds = 0;
  renderTimer();
});

ui.taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const title = ui.titleInput.value.trim();
  const deadline = ui.deadlineInput.value;
  const estimateRaw = ui.estimateInput.value.trim();

  if (!title || !deadline) {
    setFeedback("请填写任务名称和截止日期。", true);
    return;
  }

  const payload = {
    title,
    deadline,
    estimatedMinutes: estimateRaw ? Number.parseInt(estimateRaw, 10) : null,
  };

  try {
    await api("/tasks", { method: "POST", body: JSON.stringify(payload) });
    ui.taskForm.reset();
    await refreshState();
    setFeedback("任务已添加。");
  } catch (error) {
    setFeedback(`添加任务失败：${error.message}`, true);
  }
});

ui.generateBtn.addEventListener("click", async () => {
  if (ui.generateBtn.disabled) return;
  setGenerateLoading(true);
  try {
    const result = await api("/plans/today", { method: "POST" });
    await refreshState();
    setFeedback(`今日计划已生成。规划器：${result.planner || state.planner}`);
  } catch (error) {
    setFeedback(`生成计划失败：${error.message}`, true);
  } finally {
    setGenerateLoading(false);
  }
});

ui.timelineCanvas.addEventListener("dblclick", async (event) => {
  const block = event.target.closest(".timeline-block");
  if (!block) return;
  const taskId = block.dataset.taskId;
  if (!taskId) return;

  try {
    await markTaskDone(taskId, true);
    await refreshState();
    setFeedback("任务已完成，已从时间轴移除。");
  } catch (error) {
    setFeedback(`标记完成失败：${error.message}`, true);
  }
});

ui.planList.addEventListener("click", async (event) => {
  const check = event.target.closest(".task-check");
  if (!check) return;
  const taskId = check.dataset.taskId;
  const task = state.tasks.find((t) => t.id === taskId);
  if (!task) return;

  const willDone = task.status !== "done";
  try {
    await markTaskDone(taskId, willDone);
    await refreshState();
  } catch (error) {
    setFeedback(`更新任务状态失败：${error.message}`, true);
  }
});

async function bootstrap() {
  renderTimer();
  switchPage("home");
  setFeedback("准备就绪。请先在计划列表里添加任务。");
  await refreshState();
}

function switchPage(pageName) {
  state.activePage = pageName;
  ui.pages.forEach((page) => {
    page.classList.toggle("page-active", page.dataset.page === pageName);
  });
  ui.navItems.forEach((item) => {
    item.classList.toggle("nav-active", item.dataset.nav === pageName);
  });
}

function renderTimer() {
  const h = String(Math.floor(state.timerSeconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((state.timerSeconds % 3600) / 60)).padStart(2, "0");
  const s = String(state.timerSeconds % 60).padStart(2, "0");
  ui.timerDisplay.textContent = `${h}:${m}:${s}`;
}

function setGenerateLoading(loading) {
  ui.generateBtn.disabled = loading;
  ui.generateBtn.classList.toggle("loading", loading);
  ui.generateSpinner.setAttribute("aria-hidden", loading ? "false" : "true");
}

async function refreshState() {
  const data = await api("/state");
  state.tasks = data.tasks || [];
  state.todayPlan = data.todayPlan || null;
  state.checkins = data.checkins || [];
  state.planner = data.planner || "none";

  renderTimeline();
  renderPlanList();
}

function renderTimeline() {
  const today = formatDate(new Date());
  ui.timelineHeader.textContent = `${today} 时间轴（双击任务块完成）`;
  ui.timelineCanvas.innerHTML = "";

  const startHour = 8;
  const endHour = 24;
  const minutesPerPixel = 1;
  const pxPerMinute = 1 / minutesPerPixel;

  for (let hour = startHour; hour <= endHour; hour += 1) {
    const top = (hour - startHour) * 60 * pxPerMinute;

    const line = document.createElement("div");
    line.className = "time-line";
    line.style.top = `${top}px`;
    ui.timelineCanvas.appendChild(line);

    const label = document.createElement("div");
    label.className = "time-label";
    label.style.top = `${top}px`;
    label.textContent = `${String(hour).padStart(2, "0")}:00`;
    ui.timelineCanvas.appendChild(label);
  }

  const activeTaskIds = (state.todayPlan?.taskIds || []).filter((taskId) => {
    const task = state.tasks.find((t) => t.id === taskId);
    return task && task.status !== "done";
  });

  let cursorMinutes = 9 * 60;
  activeTaskIds.forEach((taskId) => {
    const task = state.tasks.find((t) => t.id === taskId);
    if (!task) return;

    const duration = clamp(task.estimatedMinutes || 60, 20, 180);
    const blockTop = (cursorMinutes - startHour * 60) * pxPerMinute;
    const blockHeight = duration * pxPerMinute;

    const block = document.createElement("div");
    block.className = "timeline-block";
    block.dataset.taskId = task.id;
    block.style.top = `${Math.max(0, blockTop)}px`;
    block.style.height = `${blockHeight}px`;
    block.innerHTML = `
      <p>${escapeHtml(task.title)}</p>
      <p class="ddl">DDL: ${escapeHtml(task.deadline)}</p>
    `;
    ui.timelineCanvas.appendChild(block);

    cursorMinutes += duration + 15;
  });
}

function renderPlanList() {
  ui.planList.innerHTML = "";

  const pending = state.tasks
    .filter((task) => task.status !== "done")
    .sort((a, b) => a.deadline.localeCompare(b.deadline));
  const done = state.tasks
    .filter((task) => task.status === "done")
    .sort((a, b) => a.deadline.localeCompare(b.deadline));
  const ordered = [...pending, ...done];

  if (ordered.length === 0) {
    const li = document.createElement("li");
    li.textContent = "还没有任务，先添加一个吧。";
    ui.planList.appendChild(li);
    return;
  }

  ordered.forEach((task) => {
    const doneClass = task.status === "done" ? "done" : "";
    const checkMark = task.status === "done" ? "✓" : "";

    const li = document.createElement("li");
    li.innerHTML = `
      <div class="task-item ${doneClass}">
        <div class="task-check ${task.status === "done" ? "checked" : ""}" data-task-id="${task.id}">${checkMark}</div>
        <div class="task-main">
          <div class="task-title">${escapeHtml(task.title)}</div>
          <div class="task-meta">DDL: ${escapeHtml(task.deadline)} · 预估 ${task.estimatedMinutes || 60} 分钟</div>
        </div>
      </div>
    `;
    ui.planList.appendChild(li);
  });
}

async function markTaskDone(taskId, done) {
  await api("/checkins", {
    method: "POST",
    body: JSON.stringify({
      taskId,
      done,
      actualMinutes: null,
    }),
  });
}

function setFeedback(message, isError = false) {
  ui.feedbackBox.textContent = message;
  ui.feedbackBox.style.borderColor = isError ? "#f2b8b5" : "#c7d6e9";
  ui.feedbackBox.style.background = isError ? "#fff4f4" : "#f6faff";
  ui.feedbackBox.style.color = isError ? "var(--danger)" : "#26435f";
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok) {
    throw new Error(data.message || `HTTP ${response.status}`);
  }
  return data;
}

function formatDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}
