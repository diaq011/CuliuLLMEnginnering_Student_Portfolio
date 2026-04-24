const API_BASE = window.location.origin.startsWith("http")
  ? `${window.location.origin}/api`
  : "http://127.0.0.1:5000/api";

const WEEK_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEK_LABELS = {
  mon: "周一",
  tue: "周二",
  wed: "周三",
  thu: "周四",
  fri: "周五",
  sat: "周六",
  sun: "周日",
};

const state = {
  tasks: [],
  todayPlan: null,
  selectedPlan: null,
  checkins: [],
  planner: "none",
  activePage: "home",
  selectedDate: formatDate(new Date()),
  timerSeconds: 0,
  timerRunning: false,
  timerHandle: null,
  feedbackTimer: null,
  weeklyAvailability: Object.fromEntries(WEEK_KEYS.map((k) => [k, []])),
  lastTap: { taskId: "", ts: 0 },
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
  planInfoBtn: document.getElementById("planInfoBtn"),
  timelineHeader: document.getElementById("timelineHeader"),
  timelineCanvas: document.getElementById("timelineCanvas"),
  planList: document.getElementById("planList"),
  feedbackBox: document.getElementById("feedbackBox"),
  availabilityForm: document.getElementById("availabilityForm"),
  availabilityEditor: document.getElementById("availabilityEditor"),
  copyWeekdaysBtn: document.getElementById("copyWeekdaysBtn"),
  copyAllDaysBtn: document.getElementById("copyAllDaysBtn"),
  timeOptions: document.getElementById("timeOptions"),
  prevDayBtn: document.getElementById("prevDayBtn"),
  nextDayBtn: document.getElementById("nextDayBtn"),
  selectedDateLabel: document.getElementById("selectedDateLabel"),
  weekStrip: document.getElementById("weekStrip"),
  planInfoModal: document.getElementById("planInfoModal"),
  closePlanInfoBtn: document.getElementById("closePlanInfoBtn"),
  planReasonText: document.getElementById("planReasonText"),
  planRiskList: document.getElementById("planRiskList"),
  planEstimateList: document.getElementById("planEstimateList"),
};

bootstrap().catch((error) => setFeedback(`初始化失败：${error.message}`, true));

ui.navItems.forEach((item) => item.addEventListener("click", () => switchPage(item.dataset.nav)));
ui.prevDayBtn.addEventListener("click", () => changeSelectedDate(-1));
ui.nextDayBtn.addEventListener("click", () => changeSelectedDate(1));
ui.weekStrip.addEventListener("click", async (event) => {
  const btn = event.target.closest("[data-date]");
  if (!btn) return;
  state.selectedDate = btn.dataset.date;
  await refreshSelectedDatePlan();
  renderDateSwitcher();
  renderTimeline();
});

ui.planInfoBtn.addEventListener("click", () => openPlanInfoModal());
ui.closePlanInfoBtn.addEventListener("click", () => closePlanInfoModal());
ui.planInfoModal.addEventListener("click", (e) => {
  if (e.target === ui.planInfoModal) closePlanInfoModal();
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
  if (!title || !deadline) return setFeedback("请填写任务名称和截止日期。", true);

  try {
    await api("/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        deadline,
        estimatedMinutes: estimateRaw ? Number.parseInt(estimateRaw, 10) : null,
      }),
    });
    ui.taskForm.reset();
    await refreshState();
    await refreshSelectedDatePlan();
    renderTimeline();
    renderPlanList();
    setFeedback("任务已添加。");
  } catch (error) {
    setFeedback(`添加任务失败：${error.message}`, true);
  }
});

ui.availabilityEditor.addEventListener("click", (event) => {
  const addBtn = event.target.closest("[data-add-day]");
  if (addBtn) return addAvailabilitySlot(addBtn.dataset.addDay);
  const removeBtn = event.target.closest("[data-remove-day]");
  if (removeBtn) removeAvailabilitySlot(removeBtn.dataset.removeDay, Number.parseInt(removeBtn.dataset.removeIndex, 10));
});

ui.copyWeekdaysBtn.addEventListener("click", () => {
  const source = cloneDayRanges("mon");
  ["tue", "wed", "thu", "fri"].forEach((day) => {
    state.weeklyAvailability[day] = source.map((r) => ({ ...r }));
  });
  renderAvailabilityEditor();
  setFeedback("已复制到周二到周五。");
});
ui.copyAllDaysBtn.addEventListener("click", () => {
  const source = cloneDayRanges("mon");
  WEEK_KEYS.forEach((day) => {
    state.weeklyAvailability[day] = source.map((r) => ({ ...r }));
  });
  renderAvailabilityEditor();
  setFeedback("已复制到全周。");
});

ui.availabilityForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const hadPlan = !!(state.todayPlan || state.selectedPlan);
  try {
    const payload = collectAvailabilityPayload();
    const result = await api("/settings/availability", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.weeklyAvailability = result.weeklyAvailability;
    renderAvailabilityEditor();
    setFeedback("空闲时间段已保存。");

    if (hadPlan) {
      const needReplan = window.confirm("检测到已有计划。是否基于新的空闲时段重新规划？");
      if (needReplan) {
        switchPage("timeline");
        await generatePlanForToday();
      }
    }
  } catch (error) {
    setFeedback(`保存失败：${error.message}`, true);
  }
});

ui.generateBtn.addEventListener("click", async () => {
  await generatePlanForToday();
});

ui.timelineCanvas.addEventListener("dblclick", async (event) => {
  const block = event.target.closest(".timeline-block");
  if (!block) return;
  await completeTaskFromBlock(block.dataset.taskId);
});
ui.timelineCanvas.addEventListener("click", async (event) => {
  const block = event.target.closest(".timeline-block");
  if (!block) return;
  const now = Date.now();
  const taskId = block.dataset.taskId;
  if (state.lastTap.taskId === taskId && now - state.lastTap.ts <= 350) {
    state.lastTap = { taskId: "", ts: 0 };
    await completeTaskFromBlock(taskId);
  } else {
    state.lastTap = { taskId, ts: now };
  }
});

ui.planList.addEventListener("click", async (event) => {
  const check = event.target.closest(".task-check");
  if (!check) return;
  const taskId = check.dataset.taskId;
  const task = state.tasks.find((t) => t.id === taskId);
  if (!task) return;
  try {
    await markTaskDone(taskId, task.status !== "done");
    await refreshState();
    await refreshSelectedDatePlan();
    renderTimeline();
    renderPlanList();
  } catch (error) {
    setFeedback(`更新任务状态失败：${error.message}`, true);
  }
});

async function bootstrap() {
  buildTimeOptions();
  renderTimer();
  switchPage("home");
  await refreshAvailability();
  await refreshState();
  await refreshSelectedDatePlan();
  renderDateSwitcher();
  renderTimeline();
  renderPlanList();
  setFeedback("准备就绪。可切换日子查看计划。");
}

async function changeSelectedDate(deltaDays) {
  state.selectedDate = shiftDate(state.selectedDate, deltaDays);
  await refreshSelectedDatePlan();
  renderDateSwitcher();
  renderTimeline();
}

async function generatePlanForToday() {
  if (ui.generateBtn.disabled) return;
  setGenerateLoading(true);
  try {
    const result = await api("/plans/today", { method: "POST" });
    await refreshState();
    state.selectedDate = result.plan?.date || formatDate(new Date());
    await refreshSelectedDatePlan();
    renderDateSwitcher();
    renderTimeline();
    const note = result.plan?.note ? ` ${result.plan.note}` : "";
    setFeedback(`计划已生成（${state.selectedDate}）。${note}`);
  } catch (error) {
    setFeedback(`生成计划失败：${error.message}`, true);
  } finally {
    setGenerateLoading(false);
  }
}

async function completeTaskFromBlock(taskId) {
  if (!taskId) return;
  try {
    await markTaskDone(taskId, true);
    await refreshState();
    await refreshSelectedDatePlan();
    renderTimeline();
    renderPlanList();
    setFeedback("任务已完成，已从时间轴移除。");
  } catch (error) {
    setFeedback(`标记完成失败：${error.message}`, true);
  }
}

function openPlanInfoModal() {
  const plan = state.selectedPlan || state.todayPlan;
  if (!plan || !plan.details) {
    setFeedback("当前日期暂无计划详情。", true);
    return;
  }
  ui.planReasonText.textContent = plan.details.rationale || "暂无";
  ui.planRiskList.innerHTML = "";
  (plan.details.risks || []).forEach((risk) => {
    const li = document.createElement("li");
    li.textContent = risk;
    ui.planRiskList.appendChild(li);
  });
  if ((plan.details.risks || []).length === 0) {
    const li = document.createElement("li");
    li.textContent = "暂无明显风险";
    ui.planRiskList.appendChild(li);
  }

  ui.planEstimateList.innerHTML = "";
  (plan.details.taskEstimates || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = `${item.title}：${item.estimatedMinutes} 分钟（${item.reason}）`;
    ui.planEstimateList.appendChild(li);
  });
  if ((plan.details.taskEstimates || []).length === 0) {
    const li = document.createElement("li");
    li.textContent = "暂无任务估时详情";
    ui.planEstimateList.appendChild(li);
  }
  ui.planInfoModal.classList.remove("hidden");
}

function closePlanInfoModal() {
  ui.planInfoModal.classList.add("hidden");
}

function switchPage(pageName) {
  state.activePage = pageName;
  ui.pages.forEach((page) => page.classList.toggle("page-active", page.dataset.page === pageName));
  ui.navItems.forEach((item) => item.classList.toggle("nav-active", item.dataset.nav === pageName));
}

function buildTimeOptions() {
  ui.timeOptions.innerHTML = "";
  for (let h = 0; h < 24; h += 1) {
    for (let m = 0; m < 60; m += 30) {
      const val = `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
      const op = document.createElement("option");
      op.value = val;
      ui.timeOptions.appendChild(op);
    }
  }
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

async function refreshAvailability() {
  const data = await api("/settings/availability");
  state.weeklyAvailability = data.weeklyAvailability || state.weeklyAvailability;
  renderAvailabilityEditor();
}

async function refreshState() {
  const data = await api("/state");
  state.tasks = data.tasks || [];
  state.todayPlan = data.todayPlan || null;
  state.checkins = data.checkins || [];
  state.planner = data.planner || "none";
  if (data.weeklyAvailability) {
    state.weeklyAvailability = data.weeklyAvailability;
    renderAvailabilityEditor();
  }
}

async function refreshSelectedDatePlan() {
  const data = await api(`/plans/${state.selectedDate}`);
  state.selectedPlan = data.plan || null;
}

function renderDateSwitcher() {
  const selected = parseDate(state.selectedDate);
  ui.selectedDateLabel.textContent = `${selected.getMonth() + 1}月${selected.getDate()}日`;
  const monday = startOfWeek(selected);
  ui.weekStrip.innerHTML = "";
  for (let i = 0; i < 7; i += 1) {
    const day = new Date(monday);
    day.setDate(monday.getDate() + i);
    const dayStr = formatDate(day);
    const isSelected = dayStr === state.selectedDate;
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = `week-day ${isSelected ? "active" : ""}`;
    cell.dataset.date = dayStr;
    cell.innerHTML = `<span>${"一二三四五六日"[i]}</span><strong>${day.getDate()}</strong>`;
    ui.weekStrip.appendChild(cell);
  }
}

function renderAvailabilityEditor() {
  ui.availabilityEditor.innerHTML = "";
  WEEK_KEYS.forEach((day) => {
    const row = document.createElement("div");
    row.className = "day-row";
    row.innerHTML = `
      <div class="day-row-head">
        <strong>${WEEK_LABELS[day]}</strong>
        <div class="day-row-actions"><button class="btn small" type="button" data-add-day="${day}">+ 添加时段</button></div>
      </div>
    `;
    const slotsWrap = document.createElement("div");
    slotsWrap.className = "slots-wrap";
    const ranges = state.weeklyAvailability[day] || [];
    if (ranges.length === 0) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "未设置";
      slotsWrap.appendChild(empty);
    } else {
      ranges.forEach((slot, idx) => {
        const slotRow = document.createElement("div");
        slotRow.className = "slot-row";
        slotRow.innerHTML = `
          <input class="time-input" data-day="${day}" data-index="${idx}" data-kind="start" list="timeOptions" value="${escapeHtml(slot.start)}" placeholder="开始时间">
          <span class="slot-sep">-</span>
          <input class="time-input" data-day="${day}" data-index="${idx}" data-kind="end" list="timeOptions" value="${escapeHtml(slot.end)}" placeholder="结束时间">
          <button class="btn small" type="button" data-remove-day="${day}" data-remove-index="${idx}">删除</button>
        `;
        slotsWrap.appendChild(slotRow);
      });
    }
    row.appendChild(slotsWrap);
    ui.availabilityEditor.appendChild(row);
  });
}

function addAvailabilitySlot(day) {
  if (!state.weeklyAvailability[day]) state.weeklyAvailability[day] = [];
  state.weeklyAvailability[day].push({ start: "18:00", end: "19:00" });
  renderAvailabilityEditor();
}

function removeAvailabilitySlot(day, index) {
  const arr = state.weeklyAvailability[day] || [];
  if (index >= 0 && index < arr.length) arr.splice(index, 1);
  renderAvailabilityEditor();
}

function cloneDayRanges(day) {
  return (state.weeklyAvailability[day] || []).map((r) => ({ ...r }));
}

function normalizeTimeText(raw) {
  let t = String(raw || "").trim().replace("：", ":").replace(".", ":");
  if (!t) throw new Error("时间不能为空");
  if (t.includes(":")) {
    const [hRaw, mRaw = "00"] = t.split(":");
    if (!/^\d{1,2}$/.test(hRaw) || !/^\d{1,2}$/.test(mRaw)) throw new Error("时间格式必须是 HH:MM");
    const h = Number.parseInt(hRaw, 10);
    const m = Number.parseInt(mRaw, 10);
    if (h < 0 || h > 23 || m < 0 || m > 59) throw new Error("时间超出范围");
    return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
  }
  if (!/^\d{1,4}$/.test(t)) throw new Error("时间格式必须是 HH:MM");
  let h = 0;
  let m = 0;
  if (t.length <= 2) h = Number.parseInt(t, 10);
  else if (t.length === 3) {
    h = Number.parseInt(t.slice(0, 1), 10);
    m = Number.parseInt(t.slice(1), 10);
  } else {
    h = Number.parseInt(t.slice(0, 2), 10);
    m = Number.parseInt(t.slice(2), 10);
  }
  if (h < 0 || h > 23 || m < 0 || m > 59) throw new Error("时间超出范围");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function hhmmToMinutes(hhmm) {
  const [h, m] = hhmm.split(":").map((x) => Number.parseInt(x, 10));
  return h * 60 + m;
}

function collectAvailabilityPayload() {
  const inputs = Array.from(ui.availabilityEditor.querySelectorAll(".time-input"));
  const grouped = {};
  inputs.forEach((input) => {
    const day = input.dataset.day;
    const idx = Number.parseInt(input.dataset.index, 10);
    const kind = input.dataset.kind;
    if (!grouped[day]) grouped[day] = {};
    if (!grouped[day][idx]) grouped[day][idx] = {};
    grouped[day][idx][kind] = input;
  });

  const payload = {};
  WEEK_KEYS.forEach((day) => {
    const rows = grouped[day] || {};
    const slotEntries = Object.keys(rows)
      .map((k) => Number.parseInt(k, 10))
      .sort((a, b) => a - b)
      .map((idx) => rows[idx]);
    const daySlots = slotEntries.map((entry) => {
      const startNorm = normalizeTimeText(entry.start.value);
      const endNorm = normalizeTimeText(entry.end.value);
      entry.start.value = startNorm;
      entry.end.value = endNorm;
      const s = hhmmToMinutes(startNorm);
      const e = hhmmToMinutes(endNorm);
      if (e <= s) throw new Error(`${WEEK_LABELS[day]}存在结束时间早于开始时间`);
      return { start: startNorm, end: endNorm, s, e };
    });
    daySlots.sort((a, b) => a.s - b.s);
    for (let i = 1; i < daySlots.length; i += 1) {
      if (daySlots[i].s < daySlots[i - 1].e) throw new Error(`${WEEK_LABELS[day]}存在重叠时段`);
    }
    payload[day] = daySlots.map((slot) => ({ start: slot.start, end: slot.end }));
    state.weeklyAvailability[day] = payload[day].map((r) => ({ ...r }));
  });
  return payload;
}

function renderTimeline() {
  const plan = state.selectedPlan;
  const blocks = plan?.scheduledBlocks || [];
  ui.timelineHeader.textContent = `${state.selectedDate} 时间轴（双击任务块完成）`;
  ui.timelineCanvas.innerHTML = "";
  const startHour = 6;
  const endHour = 24;
  const pxPerMinute = 1;

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

  blocks.forEach((block) => {
    const task = state.tasks.find((t) => t.id === block.taskId);
    if (!task || task.status === "done") return;
    const blockTop = (block.startMinute - startHour * 60) * pxPerMinute;
    const blockHeight = Math.max((block.endMinute - block.startMinute) * pxPerMinute, 20);
    const el = document.createElement("div");
    el.className = "timeline-block";
    el.dataset.taskId = block.taskId;
    el.style.top = `${Math.max(0, blockTop)}px`;
    el.style.height = `${blockHeight}px`;
    el.innerHTML = `
      <p>${escapeHtml(block.title || task.title)}</p>
      <p class="ddl">${escapeHtml(minutesToHHMM(block.startMinute))}-${escapeHtml(minutesToHHMM(block.endMinute))} · DDL: ${escapeHtml(block.deadline || task.deadline)}</p>
    `;
    ui.timelineCanvas.appendChild(el);
  });
}

function renderPlanList() {
  ui.planList.innerHTML = "";
  const pending = state.tasks.filter((task) => task.status !== "done").sort((a, b) => a.deadline.localeCompare(b.deadline));
  const done = state.tasks.filter((task) => task.status === "done").sort((a, b) => a.deadline.localeCompare(b.deadline));
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
  await api("/checkins", { method: "POST", body: JSON.stringify({ taskId, done, actualMinutes: null }) });
}

function setFeedback(message, isError = false) {
  if (state.feedbackTimer) clearTimeout(state.feedbackTimer);
  ui.feedbackBox.textContent = message;
  ui.feedbackBox.classList.remove("hidden");
  ui.feedbackBox.style.borderColor = isError ? "#f2b8b5" : "#c7d6e9";
  ui.feedbackBox.style.background = isError ? "#fff4f4" : "#f6faff";
  ui.feedbackBox.style.color = isError ? "var(--danger)" : "#26435f";
  state.feedbackTimer = setTimeout(() => ui.feedbackBox.classList.add("hidden"), 2000);
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (!response.ok) throw new Error(data.message || `HTTP ${response.status}`);
  return data;
}

function parseDate(dateStr) {
  return new Date(`${dateStr}T00:00:00`);
}

function formatDate(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function shiftDate(dateStr, deltaDays) {
  const dt = parseDate(dateStr);
  dt.setDate(dt.getDate() + deltaDays);
  return formatDate(dt);
}

function startOfWeek(date) {
  const dt = new Date(date);
  const day = dt.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  dt.setDate(dt.getDate() + diff);
  return dt;
}

function minutesToHHMM(minutes) {
  const m = Math.max(0, Math.min(minutes, 24 * 60));
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
