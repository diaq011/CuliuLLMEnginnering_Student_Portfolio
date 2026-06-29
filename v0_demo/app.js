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

const SUBJECT_LABELS = {
  chinese: "语文",
  math: "数学",
  english: "英语",
  physics: "物理",
  chemistry: "化学",
  biology: "生物",
  history: "历史",
  politics: "政治",
  geography: "地理",
  general: "综合/其他",
};

const TASK_TYPE_LABELS = {
  test_paper: "试卷",
  exercise_set: "习题/刷题",
  essay: "作文/写作",
  reading: "阅读",
  recitation: "背诵",
  vocabulary: "单词/词组",
  mistake_review: "错题整理",
  chapter_review: "章节复习",
  preview: "预习",
  lab_report: "实验报告",
  group_work: "小组作业",
  presentation: "展示/PPT",
};

const DIFFICULTY_LABELS = {
  easy: "简单",
  medium: "普通",
  hard: "困难",
};

const ASSISTANT_INTRO =
  "嗨，我是你的「J人模拟器」学习规划助手 👋\n" +
  "你不用去填复杂的表单，直接跟我说就行：\n" +
  "• 告诉我你什么时候有空，比如「工作日晚上7点到9点有空，周末下午2点到5点」\n" +
  "• 告诉我你要做的任务和截止时间，比如「数学卷3张，周一前；英语作文2篇，周三前」\n" +
  "• 说一句「帮我排计划」，我就会按你的空闲时间把任务排到 DDL 之前。\n" +
  "想从哪一件开始？";

const state = {
  authToken: localStorage.getItem("auth_token") || "",
  currentUser: "",
  tasks: [],
  todayPlan: null,
  selectedPlan: null,
  checkins: [],
  planner: "none",
  activePage: "chat",
  planStale: localStorage.getItem("plan_stale") === "1",
  editingTaskId: "",
  profileName: localStorage.getItem("profile_name") || "",
  selectedDate: formatDate(new Date()),
  timerSeconds: 0,
  timerRunning: false,
  timerHandle: null,
  focusBlockStartAt: "",
  focusSessionStartAt: "",
  focusElapsedMs: 0,
  focusDisplayMode: localStorage.getItem("focus_display_mode") || "elapsed",
  focusContent: localStorage.getItem("focus_content") || "",
  focusBlocks: loadFocusBlocks(),
  timelineBlockEdits: loadTimelineBlockEdits(),
  editingTimelineBlock: null,
  focusBubbleDrag: null,
  feedbackTimer: null,
  weeklyAvailability: Object.fromEntries(WEEK_KEYS.map((k) => [k, []])),
  availabilityChatMessages: [],
  availabilityChatSending: false,
  assistantMessages: loadAssistantMessages(),
  assistantChatSending: false,
  lastTap: { taskId: "", ts: 0 },
};

const ui = {
  pages: Array.from(document.querySelectorAll(".page")),
  navItems: Array.from(document.querySelectorAll(".nav-item")),
  timerDisplay: document.getElementById("timerDisplay"),
  timerToggleBtn: document.getElementById("timerToggleBtn"),
  timerResetBtn: document.getElementById("timerResetBtn"),
  homeAccountBtn: document.getElementById("homeAccountBtn"),
  taskForm: document.getElementById("taskForm"),
  taskCreateView: document.getElementById("taskCreateView"),
  taskListView: document.getElementById("taskListView"),
  openTaskCreateBtn: document.getElementById("openTaskCreateBtn"),
  backTaskListBtn: document.getElementById("backTaskListBtn"),
  titleInput: document.getElementById("titleInput"),
  deadlineInput: document.getElementById("deadlineInput"),
  subjectInput: document.getElementById("subjectInput"),
  taskTypeInput: document.getElementById("taskTypeInput"),
  difficultyInput: document.getElementById("difficultyInput"),
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
  settingsHome: document.getElementById("settingsHome"),
  availabilityModeSettings: document.getElementById("availabilityModeSettings"),
  availabilityAiSettings: document.getElementById("availabilityAiSettings"),
  availabilitySettings: document.getElementById("availabilitySettings"),
  openAvailabilityAiBtn: document.getElementById("openAvailabilityAiBtn"),
  openAvailabilityManualBtn: document.getElementById("openAvailabilityManualBtn"),
  backFromAvailabilityModeBtn: document.getElementById("backFromAvailabilityModeBtn"),
  backFromAvailabilityAiBtn: document.getElementById("backFromAvailabilityAiBtn"),
  availabilityChatMessages: document.getElementById("availabilityChatMessages"),
  availabilityChatForm: document.getElementById("availabilityChatForm"),
  availabilityChatInput: document.getElementById("availabilityChatInput"),
  availabilityChatSendBtn: document.getElementById("availabilityChatSendBtn"),
  assistantChatMessages: document.getElementById("assistantChatMessages"),
  assistantChatForm: document.getElementById("assistantChatForm"),
  assistantChatInput: document.getElementById("assistantChatInput"),
  assistantChatSendBtn: document.getElementById("assistantChatSendBtn"),
  authGate: document.getElementById("authGate"),
  authGateForm: document.getElementById("authGateForm"),
  authGateTitle: document.getElementById("authGateTitle"),
  gateIdentifier: document.getElementById("gateIdentifier"),
  gatePassword: document.getElementById("gatePassword"),
  gateLoginBtn: document.getElementById("gateLoginBtn"),
  gateRegisterBtn: document.getElementById("gateRegisterBtn"),
  gateStatus: document.getElementById("gateStatus"),
  accountSettings: document.getElementById("accountSettings"),
  focusSettingsPage: document.getElementById("focusSettingsPage"),
  openAvailabilitySettingsBtn: document.getElementById("openAvailabilitySettingsBtn"),
  openAccountSettingsBtn: document.getElementById("openAccountSettingsBtn"),
  openFocusSettingsPageBtn: document.getElementById("openFocusSettingsPageBtn"),
  backSettingsBtn: document.getElementById("backSettingsBtn"),
  backAccountSettingsBtn: document.getElementById("backAccountSettingsBtn"),
  backFocusSettingsBtn: document.getElementById("backFocusSettingsBtn"),
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
  planShortageSection: document.getElementById("planShortageSection"),
  planShortageSummary: document.getElementById("planShortageSummary"),
  planShortageTaskList: document.getElementById("planShortageTaskList"),
  timeShortageModal: document.getElementById("timeShortageModal"),
  timeShortageSummary: document.getElementById("timeShortageSummary"),
  timeShortageDetailBtn: document.getElementById("timeShortageDetailBtn"),
  closeTimeShortageBtn: document.getElementById("closeTimeShortageBtn"),
  focusOverlay: document.getElementById("focusOverlay"),
  focusMinimizeBtn: document.getElementById("focusMinimizeBtn"),
  focusSettingsBtn: document.getElementById("focusSettingsBtn"),
  focusClock: document.getElementById("focusClock"),
  focusContentBtn: document.getElementById("focusContentBtn"),
  focusPauseBtn: document.getElementById("focusPauseBtn"),
  focusEndBtn: document.getElementById("focusEndBtn"),
  focusBubble: document.getElementById("focusBubble"),
  focusSettingsModal: document.getElementById("focusSettingsModal"),
  closeFocusSettingsBtn: document.getElementById("closeFocusSettingsBtn"),
  focusContentModal: document.getElementById("focusContentModal"),
  closeFocusContentBtn: document.getElementById("closeFocusContentBtn"),
  focusContentInput: document.getElementById("focusContentInput"),
  saveFocusContentBtn: document.getElementById("saveFocusContentBtn"),
  focusDisplayModeInputs: Array.from(document.querySelectorAll("input[name='focusDisplayMode']")),
  timelineEditModal: document.getElementById("timelineEditModal"),
  closeTimelineEditBtn: document.getElementById("closeTimelineEditBtn"),
  timelineEditTitleInput: document.getElementById("timelineEditTitleInput"),
  timelineEditStartInput: document.getElementById("timelineEditStartInput"),
  timelineEditEndInput: document.getElementById("timelineEditEndInput"),
  timelineEditDescriptionInput: document.getElementById("timelineEditDescriptionInput"),
  deleteTimelineBlockBtn: document.getElementById("deleteTimelineBlockBtn"),
  saveTimelineBlockBtn: document.getElementById("saveTimelineBlockBtn"),
  taskEditModal: document.getElementById("taskEditModal"),
  closeTaskEditBtn: document.getElementById("closeTaskEditBtn"),
  editTitleInput: document.getElementById("editTitleInput"),
  editDeadlineInput: document.getElementById("editDeadlineInput"),
  editSubjectInput: document.getElementById("editSubjectInput"),
  editTaskTypeInput: document.getElementById("editTaskTypeInput"),
  editDifficultyInput: document.getElementById("editDifficultyInput"),
  editEstimateInput: document.getElementById("editEstimateInput"),
  deleteTaskBtn: document.getElementById("deleteTaskBtn"),
  saveTaskEditBtn: document.getElementById("saveTaskEditBtn"),
  authForm: document.getElementById("authForm"),
  accountProfileView: document.getElementById("accountProfileView"),
  accountDisplayName: document.getElementById("accountDisplayName"),
  accountUsernameText: document.getElementById("accountUsernameText"),
  profileNameInput: document.getElementById("profileNameInput"),
  saveProfileBtn: document.getElementById("saveProfileBtn"),
  profileLogoutBtn: document.getElementById("profileLogoutBtn"),
  authUsername: document.getElementById("authUsername"),
  authPassword: document.getElementById("authPassword"),
  registerBtn: document.getElementById("registerBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  authStatus: document.getElementById("authStatus"),
};

bootstrap().catch((error) => setFeedback(`初始化失败：${error.message}`, true));

ui.authGateForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await gateLogin();
});
ui.gateRegisterBtn.addEventListener("click", async () => {
  await gateRegister();
});
ui.navItems.forEach((item) => item.addEventListener("click", () => switchPage(item.dataset.nav)));
ui.assistantChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendAssistantMessage();
});
ui.assistantChatInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    sendAssistantMessage();
  }
});
ui.openTaskCreateBtn.addEventListener("click", () => showTaskCreateView());
ui.backTaskListBtn.addEventListener("click", () => showTaskListView());
if (ui.homeAccountBtn) {
  ui.homeAccountBtn.addEventListener("click", () => {
    switchPage("settings");
    showAccountSettings();
  });
}
ui.openAvailabilitySettingsBtn.addEventListener("click", () => showAvailabilityModeSettings());
ui.openAvailabilityAiBtn.addEventListener("click", () => showAvailabilityAiSettings());
ui.openAvailabilityManualBtn.addEventListener("click", () => showAvailabilityManualSettings());
ui.backFromAvailabilityModeBtn.addEventListener("click", () => showSettingsHome());
ui.backFromAvailabilityAiBtn.addEventListener("click", () => showAvailabilityModeSettings());
ui.backSettingsBtn.addEventListener("click", () => showAvailabilityModeSettings());
ui.availabilityChatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendAvailabilityChatMessage();
});
ui.openAccountSettingsBtn.addEventListener("click", () => showAccountSettings());
ui.openFocusSettingsPageBtn.addEventListener("click", () => showFocusSettingsPage());
ui.backAccountSettingsBtn.addEventListener("click", () => showSettingsHome());
ui.backFocusSettingsBtn.addEventListener("click", () => showSettingsHome());
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
ui.closeTimeShortageBtn.addEventListener("click", () => closeTimeShortageModal());
ui.timeShortageDetailBtn.addEventListener("click", () => {
  closeTimeShortageModal();
  openPlanInfoModal();
});
ui.timeShortageModal.addEventListener("click", (event) => {
  if (event.target === ui.timeShortageModal) closeTimeShortageModal();
});

ui.authForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await login();
});
ui.registerBtn.addEventListener("click", async () => {
  await register();
});
ui.logoutBtn.addEventListener("click", async () => {
  await logout();
});

if (ui.timerToggleBtn) {
  ui.timerToggleBtn.addEventListener("click", () => openFocusOverlay(true));
}
if (ui.timerResetBtn) {
  ui.timerResetBtn.addEventListener("click", () => {
    if (state.timerHandle) clearInterval(state.timerHandle);
    state.timerHandle = null;
    state.timerRunning = false;
    state.timerSeconds = 0;
    state.focusElapsedMs = 0;
    state.focusBlockStartAt = "";
    state.focusSessionStartAt = "";
    if (ui.timerToggleBtn) ui.timerToggleBtn.textContent = "开始";
    renderTimer();
    renderFocusClock();
  });
}

ui.focusMinimizeBtn.addEventListener("click", () => minimizeFocusOverlay());
ui.focusSettingsBtn.addEventListener("click", () => openFocusSettings());
ui.closeFocusSettingsBtn.addEventListener("click", () => closeFocusSettings());
ui.focusSettingsModal.addEventListener("click", (event) => {
  if (event.target === ui.focusSettingsModal) closeFocusSettings();
});
ui.focusDisplayModeInputs.forEach((input) => {
  input.addEventListener("change", () => {
    state.focusDisplayMode = input.value;
    localStorage.setItem("focus_display_mode", state.focusDisplayMode);
    renderFocusClock();
  });
});
ui.focusContentBtn.addEventListener("click", () => editFocusContent());
ui.closeFocusContentBtn.addEventListener("click", () => closeFocusContentModal());
ui.saveFocusContentBtn.addEventListener("click", () => saveFocusContentFromModal());
ui.focusContentModal.addEventListener("click", (event) => {
  if (event.target === ui.focusContentModal) closeFocusContentModal();
});
ui.focusPauseBtn.addEventListener("click", () => toggleFocusPause());
ui.focusEndBtn.addEventListener("click", () => endFocusSession());
ui.focusBubble.addEventListener("pointerdown", startFocusBubbleDrag);
ui.focusBubble.addEventListener("pointermove", moveFocusBubble);
ui.focusBubble.addEventListener("pointerup", endFocusBubbleDrag);
ui.focusBubble.addEventListener("pointercancel", endFocusBubbleDrag);
ui.closeTimelineEditBtn.addEventListener("click", () => closeTimelineBlockEditor());
ui.timelineEditModal.addEventListener("click", (event) => {
  if (event.target === ui.timelineEditModal) closeTimelineBlockEditor();
});
ui.saveTimelineBlockBtn.addEventListener("click", () => saveTimelineBlockEdit());
ui.deleteTimelineBlockBtn.addEventListener("click", () => deleteTimelineBlockEdit());
ui.saveProfileBtn.addEventListener("click", () => saveProfileSettings());
ui.profileLogoutBtn.addEventListener("click", async () => logout());
ui.closeTaskEditBtn.addEventListener("click", () => closeTaskEditor());
ui.taskEditModal.addEventListener("click", (event) => {
  if (event.target === ui.taskEditModal) closeTaskEditor();
});
ui.saveTaskEditBtn.addEventListener("click", () => saveTaskEdit());
ui.deleteTaskBtn.addEventListener("click", () => deleteTaskFromEditor());

ui.taskForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!hasIdentity()) return setFeedback("初始化中，请稍候重试", true);
  const title = ui.titleInput.value.trim();
  const deadline = ui.deadlineInput.value;
  const subject = ui.subjectInput.value;
  const taskType = ui.taskTypeInput.value;
  const difficulty = ui.difficultyInput.value;
  const estimateRaw = ui.estimateInput.value.trim();
  if (!title || !deadline || !subject || !taskType || !difficulty) {
    return setFeedback("请填写任务名称、截止日期、学科、任务类型和难度。", true);
  }

  try {
    await api("/tasks", {
      method: "POST",
      body: JSON.stringify({
        title,
        deadline,
        subject,
        taskType,
        difficulty,
        estimatedMinutes: estimateRaw ? Number.parseInt(estimateRaw, 10) : null,
      }),
    });
    ui.taskForm.reset();
    ui.subjectInput.value = "math";
    ui.taskTypeInput.value = "test_paper";
    ui.difficultyInput.value = "medium";
    await refreshState();
    await refreshSelectedDatePlan();
    renderTimeline();
    renderPlanList();
    showTaskListView();
    markPlanStale();
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
  if (!hasIdentity()) return setFeedback("初始化中，请稍候重试", true);
  try {
    const payload = collectAvailabilityPayload();
    const result = await api("/settings/availability", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.weeklyAvailability = result.weeklyAvailability;
    renderAvailabilityEditor();
    setFeedback("空闲时间段已保存。");
  } catch (error) {
    setFeedback(`保存失败：${error.message}`, true);
  }
});

ui.generateBtn.addEventListener("click", async () => {
  await generatePlanForToday();
});

ui.timelineCanvas.addEventListener("click", async (event) => {
  const block = event.target.closest(".timeline-block");
  if (!block) return;
  openTimelineBlockEditor(block);
});

ui.planList.addEventListener("click", async (event) => {
  if (!hasIdentity()) return;
  const menu = event.target.closest("[data-task-menu]");
  if (menu) {
    openTaskEditor(menu.dataset.taskMenu);
    return;
  }
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
    markPlanStale();
  } catch (error) {
    setFeedback(`更新任务状态失败：${error.message}`, true);
  }
});

function renderAuthStatus() {
  ui.authStatus.textContent = state.currentUser ? `当前账号：${state.currentUser}` : "未登录";
  ui.authForm.hidden = !!state.currentUser;
  ui.accountProfileView.hidden = !state.currentUser;
  ui.accountDisplayName.textContent = state.profileName || state.currentUser || "未登录";
  ui.accountUsernameText.textContent = state.currentUser ? `用户名：${state.currentUser}` : "--";
  ui.profileNameInput.value = state.profileName;
  const disabled = !hasIdentity();
  [ui.taskForm, ui.generateBtn, ui.availabilityForm, ui.planInfoBtn].forEach((el) => {
    if (!el) return;
    if (el.tagName === "FORM") {
      Array.from(el.querySelectorAll("input,button,select,textarea")).forEach((n) => {
        if (n.id === "registerBtn" || n.id === "logoutBtn" || n.id === "loginBtn") return;
        n.disabled = disabled;
      });
      return;
    }
    el.disabled = disabled;
  });
  ui.logoutBtn.disabled = !state.currentUser;
}

function saveProfileSettings() {
  state.profileName = ui.profileNameInput.value.trim();
  localStorage.setItem("profile_name", state.profileName);
  renderAuthStatus();
  setFeedback("账号资料已保存。");
}

function clearAppData() {
  state.tasks = [];
  state.todayPlan = null;
  state.selectedPlan = null;
  state.checkins = [];
  state.planner = "none";
  state.weeklyAvailability = Object.fromEntries(WEEK_KEYS.map((k) => [k, []]));
  renderAvailabilityEditor();
  renderTimeline();
  renderPlanList();
}

async function loadIdentityData() {
  if (!hasIdentity()) return;
  await refreshAvailability();
  await refreshState();
  await refreshSelectedDatePlan();
}

async function tryRestoreSession() {
  if (!state.authToken) {
    renderAuthStatus();
    try {
      await loadIdentityData();
    } catch {
      // guest data load failed (e.g. backend offline); keep defaults
    }
    return;
  }
  try {
    const me = await api("/auth/me");
    state.currentUser = me.user?.username || "";
    await loadIdentityData();
  } catch {
    state.authToken = "";
    state.currentUser = "";
    localStorage.removeItem("auth_token");
    clearAppData();
    try {
      await loadIdentityData();
    } catch {
      // ignore guest fallback load error
    }
  }
  renderAuthStatus();
}

async function register() {
  const username = ui.authUsername.value.trim();
  const password = ui.authPassword.value;
  if (!username || !password) return setFeedback("请输入用户名和密码", true);
  try {
    const result = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      authOptional: true,
    });
    state.authToken = result.token || "";
    state.currentUser = result.user?.username || username;
    localStorage.setItem("auth_token", state.authToken);
    await refreshAvailability();
    await refreshState();
    await refreshSelectedDatePlan();
    renderDateSwitcher();
    renderTimeline();
    renderPlanList();
    renderAuthStatus();
    setFeedback(`注册并登录成功：${state.currentUser}`);
  } catch (error) {
    setFeedback(`注册失败：${error.message}`, true);
  }
}

async function login() {
  const username = ui.authUsername.value.trim();
  const password = ui.authPassword.value;
  if (!username || !password) return setFeedback("请输入用户名和密码", true);
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
      authOptional: true,
    });
    state.authToken = result.token || "";
    state.currentUser = result.user?.username || username;
    localStorage.setItem("auth_token", state.authToken);
    await refreshAvailability();
    await refreshState();
    await refreshSelectedDatePlan();
    renderDateSwitcher();
    renderTimeline();
    renderPlanList();
    renderAuthStatus();
    setFeedback(`登录成功：${state.currentUser}`);
  } catch (error) {
    setFeedback(`登录失败：${error.message}`, true);
  }
}

async function logout() {
  try {
    if (state.authToken) {
      await api("/auth/logout", { method: "POST" });
    }
  } catch {
    // ignore
  }
  state.authToken = "";
  state.currentUser = "";
  localStorage.removeItem("auth_token");
  clearAppData();
  renderAuthStatus();
  resetAssistantConversation();
  if (ui.gateIdentifier) ui.gateIdentifier.value = "";
  if (ui.gatePassword) ui.gatePassword.value = "";
  showAuthGate("已退出登录，请重新登录。");
}

async function bootstrap() {
  buildTimeOptions();
  renderAvailabilityEditor();
  renderTimer();
  renderFocusClock();
  renderFocusContent();
  syncFocusSettingsInputs();
  renderAssistantChat();
  switchPage("chat");
  await tryRestoreSession();
  renderDateSwitcher();
  renderTimeline();
  renderPlanList();
  if (state.currentUser) {
    hideAuthGate();
    setFeedback(`已登录：${state.currentUser}`);
  } else {
    showAuthGate();
  }
}

async function changeSelectedDate(deltaDays) {
  if (!hasIdentity()) return;
  state.selectedDate = shiftDate(state.selectedDate, deltaDays);
  await refreshSelectedDatePlan();
  renderDateSwitcher();
  renderTimeline();
}

async function generatePlanForToday() {
  if (!hasIdentity()) return setFeedback("初始化中，请稍候重试", true);
  if (ui.generateBtn.disabled) return;
  setGenerateLoading(true);
  try {
    const result = await api("/plans/today", { method: "POST" });
    await refreshState();
    state.selectedDate = result.plan?.date || formatDate(new Date());
    await refreshSelectedDatePlan();
    renderDateSwitcher();
    renderTimeline();
    clearPlanStale();
    const note = result.plan?.note ? ` ${result.plan.note}` : "";
    setFeedback(`计划已生成（${state.selectedDate}）。${note}`);
    showTimeShortageModal(result.plan);
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

function formatDurationMinutes(minutes) {
  const total = Math.max(0, Number(minutes) || 0);
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours > 0 && mins > 0) return `${hours} 小时 ${mins} 分钟`;
  if (hours > 0) return `${hours} 小时`;
  return `${mins} 分钟`;
}

function buildTimeShortageSummary(shortage) {
  if (!shortage?.hasShortage) return "";
  const parts = [
    `即使排满所有空闲时段，仍无法在截止日期前完成全部任务。`,
    `共需 ${formatDurationMinutes(shortage.totalNeededMinutes)}，可用 ${formatDurationMinutes(shortage.totalAvailableMinutes)}，`,
    `缺少 ${formatDurationMinutes(shortage.shortageMinutes)}。`,
  ];
  const affected = shortage.affectedTasks || [];
  if (affected.length > 0) {
    parts.push(`涉及 ${affected.length} 个任务未能完全排入。`);
  }
  return parts.join("");
}

function renderTimeShortageDetails(shortage, summaryEl, listEl, sectionEl) {
  if (!shortage?.hasShortage) {
    if (sectionEl) sectionEl.hidden = true;
    return;
  }
  if (sectionEl) sectionEl.hidden = false;
  if (summaryEl) summaryEl.textContent = buildTimeShortageSummary(shortage);
  if (!listEl) return;
  listEl.innerHTML = "";
  (shortage.affectedTasks || []).forEach((task) => {
    const li = document.createElement("li");
    li.textContent = `${task.title}（DDL ${task.deadline}）：还需 ${formatDurationMinutes(task.shortageMinutes)}（已排 ${formatDurationMinutes(task.scheduledMinutes)} / 需 ${formatDurationMinutes(task.estimatedMinutes)}）`;
    listEl.appendChild(li);
  });
  if ((shortage.affectedTasks || []).length === 0) {
    const li = document.createElement("li");
    li.textContent = "总空闲时间不足，建议减少任务量或增加空闲时段。";
    listEl.appendChild(li);
  }
}

function showTimeShortageModal(plan) {
  const shortage = plan?.details?.timeShortage;
  if (!shortage?.hasShortage) return;
  ui.timeShortageSummary.textContent = buildTimeShortageSummary(shortage);
  ui.timeShortageModal.classList.remove("hidden");
}

function closeTimeShortageModal() {
  ui.timeShortageModal.classList.add("hidden");
}

function openPlanInfoModal() {
  const plan = state.selectedPlan || state.todayPlan;
  if (!plan || !plan.details) {
    setFeedback("当前日期暂无计划详情。", true);
    return;
  }
  renderTimeShortageDetails(
    plan.details.timeShortage,
    ui.planShortageSummary,
    ui.planShortageTaskList,
    ui.planShortageSection,
  );
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
  if (pageName === "settings") showSettingsHome();
  if (pageName === "plan") showTaskListView();
}

function markPlanStale() {
  state.planStale = true;
  localStorage.setItem("plan_stale", "1");
  renderTimeline();
}

function clearPlanStale() {
  state.planStale = false;
  localStorage.removeItem("plan_stale");
  renderTimeline();
}

function showTaskCreateView() {
  ui.taskCreateView.hidden = false;
  ui.taskListView.hidden = true;
  ui.openTaskCreateBtn.hidden = true;
}

function showTaskListView() {
  ui.taskCreateView.hidden = true;
  ui.taskListView.hidden = false;
  ui.openTaskCreateBtn.hidden = false;
}

function hideAllSettingsViews() {
  ui.settingsHome.hidden = true;
  ui.availabilityModeSettings.hidden = true;
  ui.availabilityAiSettings.hidden = true;
  ui.availabilitySettings.hidden = true;
  ui.accountSettings.hidden = true;
  ui.focusSettingsPage.hidden = true;
}

function showSettingsHome() {
  hideAllSettingsViews();
  ui.settingsHome.hidden = false;
}

function showAvailabilityModeSettings() {
  hideAllSettingsViews();
  ui.availabilityModeSettings.hidden = false;
}

function showAvailabilityAiSettings() {
  if (!hasIdentity()) return setFeedback("初始化中，请稍候重试", true);
  hideAllSettingsViews();
  ui.availabilityAiSettings.hidden = false;
  if (state.availabilityChatMessages.length === 0) {
    state.availabilityChatMessages = [
      {
        role: "assistant",
        content: "你好，请用自然语言告诉我你每周什么时候有空。例如：「周一到周五晚上 7 点到 9 点，周末下午 2 点到 5 点。」",
      },
    ];
  }
  renderAvailabilityChat();
  ui.availabilityChatInput.focus();
}

function showAvailabilityManualSettings() {
  hideAllSettingsViews();
  ui.availabilitySettings.hidden = false;
  renderAvailabilityEditor();
}

function showAccountSettings() {
  hideAllSettingsViews();
  ui.accountSettings.hidden = false;
}

function showFocusSettingsPage() {
  hideAllSettingsViews();
  ui.focusSettingsPage.hidden = false;
  syncFocusSettingsInputs();
}

function renderAvailabilityChat() {
  ui.availabilityChatMessages.innerHTML = "";
  state.availabilityChatMessages.forEach((msg) => {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${msg.role === "user" ? "user" : "assistant"}`;
    bubble.textContent = msg.content;
    ui.availabilityChatMessages.appendChild(bubble);
  });
  if (state.availabilityChatSending) {
    const pending = document.createElement("div");
    pending.className = "chat-bubble assistant pending";
    pending.textContent = "正在解析…";
    ui.availabilityChatMessages.appendChild(pending);
  }
  ui.availabilityChatMessages.scrollTop = ui.availabilityChatMessages.scrollHeight;
}

function summarizeAvailabilityForChat(availability) {
  const lines = WEEK_KEYS.map((day) => {
    const slots = availability?.[day] || [];
    if (!slots.length) return `${WEEK_LABELS[day]}：无`;
    const slotText = slots.map((slot) => `${slot.start}-${slot.end}`).join("、");
    return `${WEEK_LABELS[day]}：${slotText}`;
  });
  return lines.join("\n");
}

async function sendAvailabilityChatMessage() {
  if (!hasIdentity()) return setFeedback("初始化中，请稍候重试", true);
  if (state.availabilityChatSending) return;
  const message = ui.availabilityChatInput.value.trim();
  if (!message) return;
  state.availabilityChatMessages.push({ role: "user", content: message });
  ui.availabilityChatInput.value = "";
  state.availabilityChatSending = true;
  ui.availabilityChatSendBtn.disabled = true;
  renderAvailabilityChat();
  try {
    const history = state.availabilityChatMessages.slice(0, -1).map((msg) => ({
      role: msg.role,
      content: msg.content,
    }));
    const result = await api("/settings/availability/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    });
    let reply = result.reply || "已处理你的描述。";
    if (result.applied && result.weeklyAvailability) {
      state.weeklyAvailability = result.weeklyAvailability;
      reply = `${reply}\n\n已保存为：\n${summarizeAvailabilityForChat(result.weeklyAvailability)}`;
    } else if (result.has_time_info === false) {
      reply = result.reply || "请具体描述你的空闲时间，例如：工作日晚上 7 点到 9 点有空。";
    }
    state.availabilityChatMessages.push({ role: "assistant", content: reply });
  } catch (error) {
    state.availabilityChatMessages.push({
      role: "assistant",
      content: `解析失败：${error.message}`,
    });
  } finally {
    state.availabilityChatSending = false;
    ui.availabilityChatSendBtn.disabled = false;
    renderAvailabilityChat();
  }
}

function hasIdentity() {
  return !!state.currentUser;
}

function showAuthGate(message = "") {
  if (!ui.authGate) return;
  ui.authGate.classList.remove("hidden");
  setGateStatus(message, false);
  if (ui.gateIdentifier) ui.gateIdentifier.focus();
}

function hideAuthGate() {
  if (!ui.authGate) return;
  ui.authGate.classList.add("hidden");
}

function setGateStatus(message, isError = true) {
  if (!ui.gateStatus) return;
  ui.gateStatus.textContent = message || "";
  ui.gateStatus.style.color = isError ? "var(--danger)" : "#2c7a3f";
}

function setGateLoading(loading) {
  if (ui.gateLoginBtn) ui.gateLoginBtn.disabled = loading;
  if (ui.gateRegisterBtn) ui.gateRegisterBtn.disabled = loading;
}

function validIdentifier(value) {
  const v = String(value || "").trim().toLowerCase();
  const isPhone = /^1[3-9]\d{9}$/.test(v);
  const isEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v);
  return isPhone || isEmail;
}

function resetAssistantConversation() {
  state.assistantMessages = [{ role: "assistant", content: ASSISTANT_INTRO }];
  saveAssistantMessages();
  renderAssistantChat();
}

async function enterAppAfterAuth() {
  hideAuthGate();
  switchPage("chat");
  await loadIdentityData();
  renderDateSwitcher();
  renderTimeline();
  renderPlanList();
  renderAuthStatus();
}

async function gateLogin() {
  const identifier = ui.gateIdentifier.value.trim().toLowerCase();
  const password = ui.gatePassword.value;
  if (!validIdentifier(identifier)) return setGateStatus("请输入有效的手机号或邮箱");
  if (password.length < 6) return setGateStatus("密码至少 6 位");
  setGateLoading(true);
  setGateStatus("登录中…", false);
  try {
    const result = await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
      authOptional: true,
    });
    state.authToken = result.token || "";
    state.currentUser = result.user?.username || identifier;
    localStorage.setItem("auth_token", state.authToken);
    ui.gatePassword.value = "";
    await enterAppAfterAuth();
    setFeedback(`欢迎回来：${state.currentUser}`);
  } catch (error) {
    setGateStatus(error.message || "登录失败");
  } finally {
    setGateLoading(false);
  }
}

async function gateRegister() {
  const identifier = ui.gateIdentifier.value.trim().toLowerCase();
  const password = ui.gatePassword.value;
  if (!validIdentifier(identifier)) return setGateStatus("请输入有效的手机号或邮箱");
  if (password.length < 6) return setGateStatus("密码至少 6 位");
  setGateLoading(true);
  setGateStatus("正在创建账号…", false);
  try {
    const result = await api("/auth/register", {
      method: "POST",
      body: JSON.stringify({ identifier, password }),
      authOptional: true,
    });
    state.authToken = result.token || "";
    state.currentUser = result.user?.username || identifier;
    localStorage.setItem("auth_token", state.authToken);
    ui.gatePassword.value = "";
    resetAssistantConversation();
    await enterAppAfterAuth();
    setFeedback(`注册成功，欢迎加入：${state.currentUser}`);
  } catch (error) {
    setGateStatus(error.message || "注册失败");
  } finally {
    setGateLoading(false);
  }
}

function loadAssistantMessages() {
  try {
    const raw = localStorage.getItem("assistant_messages");
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed) && parsed.length) return parsed;
  } catch {
    // fall through to intro
  }
  return [{ role: "assistant", content: ASSISTANT_INTRO }];
}

function saveAssistantMessages() {
  try {
    localStorage.setItem("assistant_messages", JSON.stringify(state.assistantMessages.slice(-40)));
  } catch {
    // ignore quota errors
  }
}

function renderAssistantChat() {
  if (!ui.assistantChatMessages) return;
  ui.assistantChatMessages.innerHTML = "";
  state.assistantMessages.forEach((msg) => {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${msg.role === "user" ? "user" : "assistant"}`;
    bubble.textContent = msg.content;
    ui.assistantChatMessages.appendChild(bubble);
  });
  if (state.assistantChatSending) {
    const pending = document.createElement("div");
    pending.className = "chat-bubble assistant pending";
    pending.textContent = "正在思考…";
    ui.assistantChatMessages.appendChild(pending);
  }
  ui.assistantChatMessages.scrollTop = ui.assistantChatMessages.scrollHeight;
}

async function applyAssistantStateChange(changed) {
  if (!changed || (!changed.tasks && !changed.availability && !changed.plan)) return;
  try {
    await refreshState();
    if (changed.availability) renderAvailabilityEditor();
    if (changed.plan) {
      await refreshSelectedDatePlan();
      clearPlanStale();
    } else if (changed.tasks) {
      markPlanStale();
    }
    renderDateSwitcher();
    renderTimeline();
    renderPlanList();
  } catch {
    // refresh failures shouldn't break the chat reply
  }
}

async function sendAssistantMessage() {
  if (state.assistantChatSending) return;
  const message = ui.assistantChatInput.value.trim();
  if (!message) return;
  state.assistantMessages.push({ role: "user", content: message });
  ui.assistantChatInput.value = "";
  state.assistantChatSending = true;
  ui.assistantChatSendBtn.disabled = true;
  renderAssistantChat();
  saveAssistantMessages();
  try {
    const history = state.assistantMessages
      .slice(0, -1)
      .filter((m) => m.role === "user" || m.role === "assistant")
      .map((m) => ({ role: m.role, content: m.content }));
    const result = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ message, history }),
    });
    const reply = (result.reply || "").trim() || "我已经处理好了。";
    state.assistantMessages.push({ role: "assistant", content: reply });
    await applyAssistantStateChange(result.stateChanged || {});
  } catch (error) {
    state.assistantMessages.push({ role: "assistant", content: `抱歉，出错了：${error.message}` });
  } finally {
    state.assistantChatSending = false;
    ui.assistantChatSendBtn.disabled = false;
    renderAssistantChat();
    saveAssistantMessages();
  }
}

function showSettingsAvailability() {
  showAvailabilityManualSettings();
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
  if (!ui.timerDisplay) return;
  ui.timerDisplay.textContent = formatDuration(state.timerSeconds);
}

function formatDuration(totalSeconds) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds));
  const h = String(Math.floor(safeSeconds / 3600)).padStart(2, "0");
  const m = String(Math.floor((safeSeconds % 3600) / 60)).padStart(2, "0");
  const s = String(safeSeconds % 60).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function formatClock(date = new Date()) {
  const h = String(date.getHours()).padStart(2, "0");
  const m = String(date.getMinutes()).padStart(2, "0");
  const s = String(date.getSeconds()).padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function getFocusElapsedMs() {
  const liveMs = state.timerRunning && state.focusSessionStartAt
    ? Date.now() - new Date(state.focusSessionStartAt).getTime()
    : 0;
  return state.focusElapsedMs + liveMs;
}

function renderFocusClock() {
  const elapsedSeconds = Math.floor(getFocusElapsedMs() / 1000);
  state.timerSeconds = elapsedSeconds;
  renderTimer();
  ui.focusClock.textContent = state.focusDisplayMode === "clock" ? formatClock() : formatDuration(elapsedSeconds);
}

function renderFocusContent() {
  ui.focusContentBtn.textContent = state.focusContent.trim() || "未填写";
}

function ensureFocusTicker() {
  if (state.timerHandle) return;
  state.timerHandle = setInterval(() => {
    renderFocusClock();
  }, 500);
}

function stopFocusTickerIfIdle() {
  if (!state.timerHandle || state.timerRunning) return;
  if (state.focusDisplayMode === "clock" && !ui.focusOverlay.classList.contains("hidden")) return;
  clearInterval(state.timerHandle);
  state.timerHandle = null;
}

function openFocusOverlay(shouldStart) {
  ui.focusOverlay.classList.remove("hidden");
  ui.focusBubble.classList.add("hidden");
  ui.focusContentBtn.disabled = true;
  ui.focusEndBtn.disabled = true;
  window.setTimeout(() => {
    ui.focusContentBtn.disabled = false;
    ui.focusEndBtn.disabled = false;
  }, 500);
  if (shouldStart && !state.timerRunning) {
    if (!state.focusBlockStartAt) state.focusBlockStartAt = new Date().toISOString();
    state.timerRunning = true;
    state.focusSessionStartAt = new Date().toISOString();
    if (ui.timerToggleBtn) ui.timerToggleBtn.textContent = "专注中";
    ui.focusPauseBtn.textContent = "暂停";
  }
  ensureFocusTicker();
  renderFocusClock();
  renderFocusContent();
}

function minimizeFocusOverlay() {
  ui.focusOverlay.classList.add("hidden");
  ui.focusBubble.classList.remove("hidden");
}

function toggleFocusPause() {
  if (state.timerRunning) {
    state.focusElapsedMs = getFocusElapsedMs();
    state.focusSessionStartAt = "";
    state.timerRunning = false;
    ui.focusPauseBtn.textContent = "继续";
    if (ui.timerToggleBtn) ui.timerToggleBtn.textContent = "继续";
    renderFocusClock();
    stopFocusTickerIfIdle();
    return;
  }
  state.timerRunning = true;
  if (!state.focusBlockStartAt) state.focusBlockStartAt = new Date().toISOString();
  state.focusSessionStartAt = new Date().toISOString();
  ui.focusPauseBtn.textContent = "暂停";
  if (ui.timerToggleBtn) ui.timerToggleBtn.textContent = "专注中";
  ensureFocusTicker();
  renderFocusClock();
}

function editFocusContent() {
  ui.focusContentInput.value = state.focusContent;
  ui.focusContentModal.classList.remove("hidden");
  ui.focusContentInput.focus();
}

function closeFocusContentModal() {
  ui.focusContentModal.classList.add("hidden");
}

function saveFocusContentFromModal() {
  state.focusContent = ui.focusContentInput.value.trim();
  localStorage.setItem("focus_content", state.focusContent);
  renderFocusContent();
  closeFocusContentModal();
}

function openFocusSettings() {
  syncFocusSettingsInputs();
  ui.focusSettingsModal.classList.remove("hidden");
}

function closeFocusSettings() {
  ui.focusSettingsModal.classList.add("hidden");
}

function syncFocusSettingsInputs() {
  ui.focusDisplayModeInputs.forEach((input) => {
    input.checked = input.value === state.focusDisplayMode;
  });
}

function endFocusSession() {
  const elapsedMs = getFocusElapsedMs();
  const startedAt = state.focusBlockStartAt ? new Date(state.focusBlockStartAt) : new Date(Date.now() - elapsedMs);
  if (elapsedMs >= 1000) {
    addFocusTimelineBlock(startedAt, elapsedMs, state.focusContent.trim() || "未填写");
  }
  if (state.timerHandle) clearInterval(state.timerHandle);
  state.timerHandle = null;
  state.timerRunning = false;
  state.timerSeconds = 0;
  state.focusElapsedMs = 0;
  state.focusBlockStartAt = "";
  state.focusSessionStartAt = "";
  if (ui.timerToggleBtn) ui.timerToggleBtn.textContent = "开始";
  ui.focusPauseBtn.textContent = "暂停";
  ui.focusOverlay.classList.add("hidden");
  ui.focusBubble.classList.add("hidden");
  renderTimer();
  renderFocusClock();
  renderTimeline();
  setFeedback("专注记录已添加到时间轴。");
}

function startFocusBubbleDrag(event) {
  ui.focusBubble.setPointerCapture(event.pointerId);
  const rect = ui.focusBubble.getBoundingClientRect();
  state.focusBubbleDrag = {
    pointerId: event.pointerId,
    offsetX: event.clientX - rect.left,
    offsetY: event.clientY - rect.top,
    moved: false,
  };
  ui.focusBubble.classList.add("dragging");
}

function moveFocusBubble(event) {
  const drag = state.focusBubbleDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const maxLeft = window.innerWidth - ui.focusBubble.offsetWidth - 8;
  const maxTop = window.innerHeight - ui.focusBubble.offsetHeight - 8;
  const left = Math.max(8, Math.min(maxLeft, event.clientX - drag.offsetX));
  const top = Math.max(8, Math.min(maxTop, event.clientY - drag.offsetY));
  if (Math.abs(left - ui.focusBubble.offsetLeft) > 2 || Math.abs(top - ui.focusBubble.offsetTop) > 2) {
    drag.moved = true;
  }
  ui.focusBubble.style.left = `${left}px`;
  ui.focusBubble.style.top = `${top}px`;
}

function endFocusBubbleDrag(event) {
  const drag = state.focusBubbleDrag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  ui.focusBubble.releasePointerCapture(event.pointerId);
  ui.focusBubble.classList.remove("dragging");
  state.focusBubbleDrag = null;
  if (!drag.moved) openFocusOverlay(false);
}

function setGenerateLoading(loading) {
  ui.generateBtn.disabled = loading;
  ui.generateBtn.classList.toggle("loading", loading);
  ui.generateSpinner.setAttribute("aria-hidden", loading ? "false" : "true");
}

async function refreshAvailability() {
  if (!hasIdentity()) return;
  const data = await api("/settings/availability");
  state.weeklyAvailability = data.weeklyAvailability || state.weeklyAvailability;
  renderAvailabilityEditor();
}

async function refreshState() {
  if (!hasIdentity()) return;
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
  if (!state.currentUser) {
    state.selectedPlan = null;
    return;
  }
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
    const visibleRanges = ranges.length > 0 ? ranges : [{ start: "", end: "", isDraft: true }];
    visibleRanges.forEach((slot, idx) => {
      const slotRow = document.createElement("div");
      slotRow.className = `slot-row ${slot.isDraft ? "is-draft" : ""}`;
      const removeButton = slot.isDraft
        ? ""
        : `<button class="btn small" type="button" data-remove-day="${day}" data-remove-index="${idx}">删除</button>`;
      slotRow.innerHTML = `
        <input class="time-input" data-day="${day}" data-index="${idx}" data-kind="start" list="timeOptions" value="${escapeHtml(slot.start)}" placeholder="开始时间">
        <span class="slot-sep">-</span>
        <input class="time-input" data-day="${day}" data-index="${idx}" data-kind="end" list="timeOptions" value="${escapeHtml(slot.end)}" placeholder="结束时间">
        ${removeButton}
      `;
      slotsWrap.appendChild(slotRow);
    });
    if (ranges.length === 0) {
      const empty = document.createElement("p");
      empty.className = "hint";
      empty.textContent = "留空则不保存该日时段，也可以直接输入后保存。";
      slotsWrap.appendChild(empty);
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
      const startRaw = entry.start?.value.trim() || "";
      const endRaw = entry.end?.value.trim() || "";
      if (!startRaw && !endRaw) return null;
      if (!startRaw || !endRaw) throw new Error(`${WEEK_LABELS[day]}存在未填完整的时间段`);
      const startNorm = normalizeTimeText(entry.start.value);
      const endNorm = normalizeTimeText(entry.end.value);
      entry.start.value = startNorm;
      entry.end.value = endNorm;
      const s = hhmmToMinutes(startNorm);
      const e = hhmmToMinutes(endNorm);
      if (e <= s) throw new Error(`${WEEK_LABELS[day]}存在结束时间早于开始时间`);
      return { start: startNorm, end: endNorm, s, e };
    }).filter(Boolean);
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
  ui.timelineHeader.innerHTML = `${escapeHtml(state.selectedDate)} 时间轴${state.planStale ? '<span class="stale-warning">任务更改后还没重新生成计划</span>' : ""}`;
  ui.timelineCanvas.innerHTML = "";
  const content = document.createElement("div");
  content.className = "timeline-content";
  ui.timelineCanvas.appendChild(content);
  const pxPerMinute = 1;
  const renderBlocks = [];
  blocks.forEach((block) => {
    const task = state.tasks.find((t) => t.id === block.taskId);
    if (!task || task.status === "done") return;
    const key = getPlanBlockKey(block);
    const edit = state.timelineBlockEdits[key] || {};
    if (edit.deleted) return;
    const startMinute = Number.isFinite(edit.startMinute) ? edit.startMinute : block.startMinute;
    const endMinute = Number.isFinite(edit.endMinute) ? edit.endMinute : block.endMinute;
    const title = edit.title || block.title || task.title;
    const description = edit.description || "";
    renderBlocks.push({
      kind: "plan",
      key,
      taskId: block.taskId,
      startMinute,
      endMinute,
      html: `
      <p>${escapeHtml(title)}</p>
      <p class="ddl">${escapeHtml(minutesToHHMM(startMinute))}-${escapeHtml(minutesToHHMM(endMinute))} · DDL: ${escapeHtml(block.deadline || task.deadline)}</p>
      ${description ? `<p class="desc">${escapeHtml(description)}</p>` : ""}
    `,
    });
  });

  state.focusBlocks
    .filter((block) => block.date === state.selectedDate)
    .forEach((block) => {
      renderBlocks.push({
        kind: "focus",
        id: block.id,
        startMinute: block.startMinute,
        endMinute: block.endMinute,
        extraClass: "focus-block",
        html: `
        <p>${escapeHtml(block.title)}</p>
        <p class="ddl">${escapeHtml(minutesToHHMM(block.startMinute))}-${escapeHtml(minutesToHHMM(block.endMinute))} · 专注</p>
        ${block.description ? `<p class="desc">${escapeHtml(block.description)}</p>` : ""}
      `,
      });
    });

  const minBlockStart = renderBlocks.length ? Math.min(...renderBlocks.map((block) => block.startMinute)) : 6 * 60;
  const maxBlockEnd = renderBlocks.length ? Math.max(...renderBlocks.map((block) => block.endMinute)) : 24 * 60;
  const startHour = Math.max(0, Math.floor(Math.max(0, minBlockStart - 60) / 60));
  const endHour = Math.min(24, Math.max(startHour + 6, Math.ceil(Math.min(24 * 60, maxBlockEnd + 60) / 60)));
  content.style.height = `${(endHour - startHour) * 60 * pxPerMinute}px`;

  for (let hour = startHour; hour <= endHour; hour += 1) {
    const top = (hour - startHour) * 60 * pxPerMinute;
    const line = document.createElement("div");
    line.className = "time-line";
    line.style.top = `${top}px`;
    content.appendChild(line);

    const label = document.createElement("div");
    label.className = "time-label";
    label.style.top = `${top}px`;
    label.textContent = `${String(hour).padStart(2, "0")}:00`;
    content.appendChild(label);
  }

  layoutTimelineBlocks(renderBlocks).forEach((block) => {
    const blockTop = (block.startMinute - startHour * 60) * pxPerMinute;
    const blockHeight = Math.max((block.endMinute - block.startMinute) * pxPerMinute, 20);
    const el = document.createElement("div");
    el.className = `timeline-block ${block.extraClass || ""}`;
    el.dataset.blockKind = block.kind;
    if (block.key) el.dataset.blockKey = block.key;
    if (block.taskId) el.dataset.taskId = block.taskId;
    if (block.id) el.dataset.blockId = block.id;
    el.style.top = `${Math.max(0, blockTop)}px`;
    el.style.height = `${blockHeight}px`;
    el.style.left = `calc(58px + ${block.column * block.columnWidth}%)`;
    el.style.right = "auto";
    el.style.width = `calc(${block.columnWidth}% - 8px)`;
    el.innerHTML = block.html;
    content.appendChild(el);
  });
}

function layoutTimelineBlocks(blocks) {
  const sorted = [...blocks].sort((a, b) => a.startMinute - b.startMinute || a.endMinute - b.endMinute);
  const active = [];
  sorted.forEach((block) => {
    for (let i = active.length - 1; i >= 0; i -= 1) {
      if (active[i].endMinute <= block.startMinute) active.splice(i, 1);
    }
    const used = new Set(active.map((item) => item.column));
    let column = 0;
    while (used.has(column)) column += 1;
    block.column = column;
    active.push(block);
    const groupSize = Math.max(...active.map((item) => item.column)) + 1;
    active.forEach((item) => {
      item.groupSize = Math.max(item.groupSize || 1, groupSize);
    });
  });
  return sorted.map((block) => ({
    ...block,
    columnWidth: 86 / Math.max(1, block.groupSize || 1),
  }));
}

function getPlanBlockKey(block) {
  return `plan:${state.selectedDate}:${block.taskId}:${block.startMinute}:${block.endMinute}`;
}

function loadFocusBlocks() {
  try {
    const raw = localStorage.getItem("focus_blocks");
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveFocusBlocks() {
  localStorage.setItem("focus_blocks", JSON.stringify(state.focusBlocks));
}

function loadTimelineBlockEdits() {
  try {
    const raw = localStorage.getItem("timeline_block_edits");
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function saveTimelineBlockEdits() {
  localStorage.setItem("timeline_block_edits", JSON.stringify(state.timelineBlockEdits));
}

function addFocusTimelineBlock(startedAt, elapsedMs, title) {
  const startMinute = startedAt.getHours() * 60 + startedAt.getMinutes();
  const durationMinutes = Math.max(1, Math.ceil(elapsedMs / 60000));
  const endMinute = Math.min(24 * 60, startMinute + durationMinutes);
  const block = {
    id: `focus-${Date.now()}`,
    date: formatDate(startedAt),
    startMinute,
    endMinute,
    title,
    description: "",
  };
  state.focusBlocks.push(block);
  saveFocusBlocks();
  state.selectedDate = block.date;
  renderDateSwitcher();
}

function openTimelineBlockEditor(element) {
  const kind = element.dataset.blockKind;
  let data = null;
  if (kind === "focus") {
    const block = state.focusBlocks.find((item) => item.id === element.dataset.blockId);
    if (!block) return;
    data = { kind, id: block.id, title: block.title, description: block.description || "", startMinute: block.startMinute, endMinute: block.endMinute };
  } else {
    const key = element.dataset.blockKey;
    const block = (state.selectedPlan?.scheduledBlocks || []).find((item) => getPlanBlockKey(item) === key);
    if (!block) return;
    const task = state.tasks.find((item) => item.id === block.taskId);
    const edit = state.timelineBlockEdits[key] || {};
    data = {
      kind: "plan",
      key,
      title: edit.title || block.title || task?.title || "",
      description: edit.description || "",
      startMinute: Number.isFinite(edit.startMinute) ? edit.startMinute : block.startMinute,
      endMinute: Number.isFinite(edit.endMinute) ? edit.endMinute : block.endMinute,
    };
  }
  state.editingTimelineBlock = data;
  ui.timelineEditTitleInput.value = data.title;
  ui.timelineEditStartInput.value = minutesToHHMM(data.startMinute);
  ui.timelineEditEndInput.value = minutesToHHMM(data.endMinute);
  ui.timelineEditDescriptionInput.value = data.description || "";
  ui.timelineEditModal.classList.remove("hidden");
}

function closeTimelineBlockEditor() {
  ui.timelineEditModal.classList.add("hidden");
  state.editingTimelineBlock = null;
}

function readTimelineEditForm() {
  const title = ui.timelineEditTitleInput.value.trim() || "未命名";
  const description = ui.timelineEditDescriptionInput.value.trim();
  const start = normalizeTimeText(ui.timelineEditStartInput.value);
  const end = normalizeTimeText(ui.timelineEditEndInput.value);
  const startMinute = hhmmToMinutes(start);
  const endMinute = hhmmToMinutes(end);
  if (endMinute <= startMinute) throw new Error("结束时间必须晚于开始时间");
  return { title, description, startMinute, endMinute };
}

function saveTimelineBlockEdit() {
  if (!state.editingTimelineBlock) return;
  try {
    const next = readTimelineEditForm();
    if (state.editingTimelineBlock.kind === "focus") {
      const block = state.focusBlocks.find((item) => item.id === state.editingTimelineBlock.id);
      if (block) Object.assign(block, next);
      saveFocusBlocks();
    } else {
      state.timelineBlockEdits[state.editingTimelineBlock.key] = {
        ...(state.timelineBlockEdits[state.editingTimelineBlock.key] || {}),
        ...next,
        deleted: false,
      };
      saveTimelineBlockEdits();
    }
    closeTimelineBlockEditor();
    renderTimeline();
    setFeedback("时间段已更新。");
  } catch (error) {
    setFeedback(`保存失败：${error.message}`, true);
  }
}

function deleteTimelineBlockEdit() {
  if (!state.editingTimelineBlock) return;
  if (state.editingTimelineBlock.kind === "focus") {
    state.focusBlocks = state.focusBlocks.filter((item) => item.id !== state.editingTimelineBlock.id);
    saveFocusBlocks();
  } else {
    state.timelineBlockEdits[state.editingTimelineBlock.key] = {
      ...(state.timelineBlockEdits[state.editingTimelineBlock.key] || {}),
      deleted: true,
    };
    saveTimelineBlockEdits();
  }
  closeTimelineBlockEditor();
  renderTimeline();
  setFeedback("时间段已删除。");
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
    const subjectLabel = SUBJECT_LABELS[task.subject] || "综合/其他";
    const taskTypeLabel = TASK_TYPE_LABELS[task.taskType] || "习题/刷题";
    const difficultyLabel = DIFFICULTY_LABELS[task.difficulty] || "普通";
    const li = document.createElement("li");
    li.innerHTML = `
      <div class="task-item ${doneClass}">
        <div class="task-check ${task.status === "done" ? "checked" : ""}" data-task-id="${task.id}">${checkMark}</div>
        <div class="task-main">
          <div class="task-title">${escapeHtml(task.title)}</div>
          <div class="task-meta">DDL: ${escapeHtml(task.deadline)} · ${escapeHtml(subjectLabel)} · ${escapeHtml(taskTypeLabel)} · ${escapeHtml(difficultyLabel)} · 预估 ${task.estimatedMinutes || 60} 分钟</div>
        </div>
        <button class="task-menu-btn" type="button" data-task-menu="${task.id}" aria-label="编辑任务">⋯</button>
      </div>
    `;
    ui.planList.appendChild(li);
  });
}

function openTaskEditor(taskId) {
  const task = state.tasks.find((item) => item.id === taskId);
  if (!task) return;
  state.editingTaskId = taskId;
  ui.editTitleInput.value = task.title || "";
  ui.editDeadlineInput.value = task.deadline || "";
  ui.editSubjectInput.value = task.subject || "general";
  ui.editTaskTypeInput.value = task.taskType || "exercise_set";
  ui.editDifficultyInput.value = task.difficulty || "medium";
  ui.editEstimateInput.value = task.estimatedMinutes || "";
  ui.taskEditModal.classList.remove("hidden");
}

function closeTaskEditor() {
  ui.taskEditModal.classList.add("hidden");
  state.editingTaskId = "";
}

function readTaskEditorPayload() {
  const title = ui.editTitleInput.value.trim();
  const deadline = ui.editDeadlineInput.value;
  if (!title || !deadline) throw new Error("请填写任务名称和截止日期");
  const estimateRaw = ui.editEstimateInput.value.trim();
  return {
    title,
    deadline,
    subject: ui.editSubjectInput.value,
    taskType: ui.editTaskTypeInput.value,
    difficulty: ui.editDifficultyInput.value,
    estimatedMinutes: estimateRaw ? Number.parseInt(estimateRaw, 10) : null,
  };
}

async function saveTaskEdit() {
  if (!state.editingTaskId) return;
  try {
    await api(`/tasks/${state.editingTaskId}`, {
      method: "PUT",
      body: JSON.stringify(readTaskEditorPayload()),
    });
    closeTaskEditor();
    await refreshState();
    await refreshSelectedDatePlan();
    renderPlanList();
    markPlanStale();
    setFeedback("任务已更新，请重新生成计划。");
  } catch (error) {
    setFeedback(`保存任务失败：${error.message}`, true);
  }
}

async function deleteTaskFromEditor() {
  if (!state.editingTaskId) return;
  try {
    await api(`/tasks/${state.editingTaskId}`, { method: "DELETE" });
    closeTaskEditor();
    await refreshState();
    await refreshSelectedDatePlan();
    renderPlanList();
    markPlanStale();
    setFeedback("任务已删除，请重新生成计划。");
  } catch (error) {
    setFeedback(`删除任务失败：${error.message}`, true);
  }
}

async function markTaskDone(taskId, done) {
  await api("/checkins", { method: "POST", body: JSON.stringify({ taskId, done, actualMinutes: null }) });
}

function setFeedback(message, isError = false) {
  if (state.feedbackTimer) clearTimeout(state.feedbackTimer);
  ui.feedbackBox.textContent = message;
  ui.feedbackBox.classList.remove("hidden");
  ui.feedbackBox.style.borderColor = isError ? "#f2b8b5" : "#c7d6e9";
  ui.feedbackBox.style.background = isError ? "rgba(255, 244, 244, 0.82)" : "rgba(246, 250, 255, 0.82)";
  ui.feedbackBox.style.color = isError ? "var(--danger)" : "#26435f";
  state.feedbackTimer = setTimeout(() => ui.feedbackBox.classList.add("hidden"), 2000);
}

async function api(path, options = {}) {
  const authOptional = !!options.authOptional;
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.authToken) headers.Authorization = `Bearer ${state.authToken}`;
  const fetchOptions = { ...options, headers };
  delete fetchOptions.authOptional;
  const response = await fetch(`${API_BASE}${path}`, {
    ...fetchOptions,
  });
  const raw = await response.text();
  const data = raw ? JSON.parse(raw) : {};
  if (response.status === 401 && !authOptional) {
    state.authToken = "";
    state.currentUser = "";
    localStorage.removeItem("auth_token");
    clearAppData();
    renderAuthStatus();
    showAuthGate("登录已失效，请重新登录");
    throw new Error("登录已失效，请重新登录");
  }
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
