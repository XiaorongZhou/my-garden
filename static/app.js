import {
  createPhotoThumbnail,
  escapeHtml,
  formatDateOnly,
  isUnknownSuggestionName,
  localDateTimeValue,
  normalizeDiagnosis,
  normalizeSuggestion,
  normalizeTip,
  todayInputValue,
} from "/static/js/helpers.js";
import {
  createPlantChatMessageRequest,
  createSessionRequest,
  createCheckinRequest,
  createPlantRequest,
  deleteCheckinRequest,
  deletePlantRequest,
  fetchAdminMetrics,
  fetchPlantDetail,
  fetchPlantChat,
  fetchPlants,
  fetchSession,
  patchPlant,
  requestPlantIdentityPreview,
  setWateringRequest,
  setApiSessionToken,
} from "/static/js/api.js";
import {
  createInitialState,
  resetChatState,
  resetSessionState,
  resetDetailEditorState,
  resetIntakeSuggestion,
  syncDetailEditorState,
  syncIntakePlantNameFromSuggestion,
} from "/static/js/state.js";
import { routeFromHash, setRoute } from "/static/js/router.js";
import { renderAddView } from "/static/js/views/add-view.js";
import { renderGarden } from "/static/js/views/garden-view.js";
import { renderChatView } from "/static/js/views/chat-view.js";
import { renderAdminDashboard } from "/static/js/views/admin-view.js";
import {
  renderCheckinView,
  renderDetail,
  updateDetailPreviewSlot,
} from "/static/js/views/detail-view.js";

const elements = {
  authViewEl: document.getElementById("auth-view"),
  authForm: document.getElementById("auth-form"),
  authEyebrowEl: document.getElementById("auth-eyebrow"),
  authTitleEl: document.getElementById("auth-title"),
  authCopyEl: document.getElementById("auth-copy"),
  authNameFieldEl: document.getElementById("auth-name-field"),
  authNameLabelEl: document.getElementById("auth-name-label"),
  authNameInput: document.getElementById("auth-name"),
  authEmailLabelEl: document.getElementById("auth-email-label"),
  authEmailInput: document.getElementById("auth-email"),
  authPasswordLabelEl: document.getElementById("auth-password-label"),
  authPasswordInput: document.getElementById("auth-password"),
  authSubmitButton: document.getElementById("auth-submit"),
  languageButtons: Array.from(document.querySelectorAll("[data-language]")),
  sessionBarEl: document.getElementById("session-bar"),
  sessionUserNameEl: document.getElementById("session-user-name"),
  sessionUserEmailEl: document.getElementById("session-user-email"),
  adminLink: document.getElementById("admin-link"),
  switchProfileButton: document.getElementById("switch-profile"),
  gardenViewEl: document.getElementById("garden-view"),
  adminViewEl: document.getElementById("admin-view"),
  addViewEl: document.getElementById("add-view"),
  detailViewEl: document.getElementById("detail-view"),
  chatViewEl: document.getElementById("chat-view"),
  addPlantForm: document.getElementById("add-plant-form"),
  toastEl: document.getElementById("toast"),
  tabBarEl: document.querySelector(".tab-bar"),
  tabButtons: Array.from(document.querySelectorAll(".tab-button")),
  addEyebrowEl: document.getElementById("add-eyebrow"),
  addTitleEl: document.getElementById("add-title"),
  intakePhotoInput: document.getElementById("intake-photo"),
  intakeLocationLabelEl: document.getElementById("plant-location-label"),
  intakeLocationInput: document.getElementById("plant-location"),
  intakePurchaseDateLabelEl: document.getElementById("plant-purchase-date-label"),
  intakePurchaseDateInput: document.getElementById("plant-purchase-date"),
  roomOptionsEl: document.getElementById("room-options"),
  intakePreviewEl: document.getElementById("intake-photo-preview"),
  suggestionCardEl: document.getElementById("suggestion-card"),
  suggestedNameEl: document.getElementById("suggested-name"),
  suggestedChineseNameEl: document.getElementById("suggested-chinese-name"),
  suggestedSpeciesEl: document.getElementById("suggested-species"),
  suggestedMetaEl: document.getElementById("suggested-meta"),
  suggestedCaptionEl: document.getElementById("suggested-caption"),
  suggestedDiagnosisEl: document.getElementById("suggested-diagnosis"),
  suggestedDiagnosisStatusEl: document.getElementById("suggested-diagnosis-status"),
  suggestedDiagnosisTitleEl: document.getElementById("suggested-diagnosis-title"),
  suggestedDiagnosisSummaryEl: document.getElementById("suggested-diagnosis-summary"),
  suggestedTipEl: document.getElementById("suggested-tip"),
  suggestedTipTitleEl: document.getElementById("suggested-tip-title"),
  suggestedTipBodyEl: document.getElementById("suggested-tip-body"),
  plantNameInput: document.getElementById("plant-name"),
  editPlantNameButton: document.getElementById("edit-plant-name"),
  identifyPlantButton: document.getElementById("identify-plant"),
};

const state = createInitialState();
const SESSION_STORAGE_KEY = "my-garden-session-token";
const REMEMBERED_USER_STORAGE_KEY = "my-garden-remembered-user";
const LANGUAGE_STORAGE_KEY = "my-garden-language";

const COPY = {
  en: {
    auth: {
      eyebrow: "Your garden",
      openTitle: "Open your garden",
      createTitle: "Create your garden",
      claimTitle: "Claim your garden",
      openCopy: "Sign in with your email and garden password. If this is a new garden, we’ll ask for your name next.",
      createCopy: "This email is new here, so add your name once to create a new garden.",
      claimCopy: "This email is new here, so add your name once to claim the shared garden. Your password will protect it going forward.",
      name: "Your name",
      namePlaceholder: "Alicia",
      email: "Email",
      emailPlaceholder: "you@example.com",
      password: "Password",
      passwordPlaceholder: "At least 8 characters",
      continue: "Continue",
      opening: "Opening...",
    },
    tabs: {
      add: "Add Plant",
      garden: "Your Garden",
    },
    session: {
      eyebrow: "Garden",
      switch: "Switch",
      stats: "Stats",
      gardenSuffix: "garden",
    },
    add: {
      eyebrow: "New plant",
      title: "Describe your plant",
      location: "Where it lives",
      locationPlaceholder: "Choose an existing room or type a new one",
      purchaseDate: "Purchase date",
      save: "Save plant",
      saving: "Saving...",
      identify: "Identify plant",
      identifying: "Identifying...",
      reIdentify: "Re-identify plant",
      photoButton: "Take or choose photo",
      loadingName: "Looking closely...",
      loadingSpecies: "Identifying your plant",
      loadingCaption: "We’re identifying the plant and drafting a first read before you save.",
      readyName: "Ready when you are",
      readySpecies: "Photo attached",
      readyCaption: "Tap Identify plant to preview the plant name and first read before saving.",
      initialReadFallback: "Initial read saved and ready to use when you save this plant.",
      careTip: "Care tip",
      nameUnknownPlaceholder: "Give this plant a name before saving",
      nameEditPlaceholder: "Edit the plant name before saving",
    },
    garden: {
      emptyEyebrow: "No plants yet",
      emptyTitle: "Start with the camera",
      emptyCopy: "Use the Add Plant tab to snap a photo, save the plant, and create its first diagnosis.",
      eyebrow: "Your garden",
      title: "Plant list",
      plantCount: (count) => `${count} ${count === 1 ? "plant" : "plants"}`,
      home: "Home",
      fallbackSummary: "No diagnosis yet. Start with a photo check-in.",
    },
    toast: {
      addPhotoFirst: "Add a photo first",
      takePhotoFirst: "Take a photo first",
      identifyFirst: "Tap Identify plant first",
      namePlant: "Name this plant before saving",
      reidentify: "Please identify this plant again",
      savedPrefix: "Saved",
      saveError: "Could not save plant",
      authEmail: "Add your email first",
      authPassword: "Use at least 8 characters",
      authName: "Add your name to finish opening this garden",
    },
  },
  zh: {
    auth: {
      eyebrow: "你的花园",
      openTitle: "打开你的花园",
      createTitle: "创建你的花园",
      claimTitle: "认领你的花园",
      openCopy: "用邮箱和花园密码登录。如果这是新花园，下一步会请你填写名字。",
      createCopy: "这个邮箱还没有花园。填写一次名字，就可以创建你的专属花园。",
      claimCopy: "这个邮箱还没有花园。填写一次名字，就可以认领这个花园，以后用密码保护。",
      name: "你的名字",
      namePlaceholder: "Alicia",
      email: "邮箱",
      emailPlaceholder: "you@example.com",
      password: "密码",
      passwordPlaceholder: "至少 8 位",
      continue: "继续",
      opening: "正在打开...",
    },
    tabs: {
      add: "添加植物",
      garden: "我的花园",
    },
    session: {
      eyebrow: "花园",
      switch: "切换",
      stats: "数据",
      gardenSuffix: "的花园",
    },
    add: {
      eyebrow: "新植物",
      title: "描述你的植物",
      location: "放在哪里",
      locationPlaceholder: "选择已有房间，或输入新位置",
      purchaseDate: "购买日期",
      save: "保存植物",
      saving: "保存中...",
      identify: "识别植物",
      identifying: "识别中...",
      reIdentify: "重新识别",
      photoButton: "拍照或从相册选择",
      loadingName: "正在仔细看...",
      loadingSpecies: "正在识别植物",
      loadingCaption: "正在识别植物，并在保存前生成第一条健康判断。",
      readyName: "准备好了",
      readySpecies: "已添加照片",
      readyCaption: "点“识别植物”，先预览植物名称和第一条健康判断。",
      initialReadFallback: "初始判断已保存，保存植物后就能看到。",
      careTip: "养护提示",
      nameUnknownPlaceholder: "保存前给这棵植物起个名字",
      nameEditPlaceholder: "保存前可以修改植物名称",
    },
    garden: {
      emptyEyebrow: "还没有植物",
      emptyTitle: "从拍一张照片开始",
      emptyCopy: "去“添加植物”拍照或选图，保存植物，并生成第一条健康判断。",
      eyebrow: "我的花园",
      title: "植物列表",
      plantCount: (count) => `${count} 棵植物`,
      home: "家里",
      fallbackSummary: "还没有诊断。先拍一张照片做第一次记录吧。",
    },
    toast: {
      addPhotoFirst: "先添加一张照片",
      takePhotoFirst: "先拍照或选择照片",
      identifyFirst: "先点“识别植物”",
      namePlant: "保存前先给植物起个名字",
      reidentify: "请重新识别这棵植物",
      savedPrefix: "已保存",
      saveError: "暂时无法保存植物",
      authEmail: "先填写邮箱",
      authPassword: "密码至少 8 位",
      authName: "填写名字后就可以打开花园",
    },
  },
};

function t() {
  return COPY[state.language] || COPY.en;
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    return;
  }
  try {
    await navigator.serviceWorker.register("/sw.js");
  } catch (error) {
    console.warn("Service worker registration failed.", error);
  }
}

function showToast(message) {
  elements.toastEl.textContent = message;
  elements.toastEl.classList.add("show");
  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => {
    elements.toastEl.classList.remove("show");
  }, 1800);
}

function storeSessionToken(sessionToken) {
  if (sessionToken) {
    window.localStorage.setItem(SESSION_STORAGE_KEY, sessionToken);
  } else {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
  }
}

function storeRememberedUser(user) {
  if (user?.id && user?.email) {
    window.localStorage.setItem(REMEMBERED_USER_STORAGE_KEY, JSON.stringify({
      id: user.id,
      name: user.name || "",
      email: user.email || "",
    }));
    state.rememberedUser = {
      id: String(user.id),
      name: String(user.name || ""),
      email: String(user.email || ""),
    };
    return;
  }
  window.localStorage.removeItem(REMEMBERED_USER_STORAGE_KEY);
  state.rememberedUser = null;
}

function readStoredLanguage() {
  const stored = String(window.localStorage.getItem(LANGUAGE_STORAGE_KEY) || "").trim();
  return stored === "zh" ? "zh" : "en";
}

function setLanguage(language) {
  state.language = language === "zh" ? "zh" : "en";
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, state.language);
  document.documentElement.lang = state.language === "zh" ? "zh-CN" : "en";
}

function readStoredSessionToken() {
  return String(window.localStorage.getItem(SESSION_STORAGE_KEY) || "").trim();
}

function readRememberedUser() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(REMEMBERED_USER_STORAGE_KEY) || "null");
    if (!parsed?.id || !parsed?.email) {
      return null;
    }
    return {
      id: String(parsed.id),
      name: String(parsed.name || ""),
      email: String(parsed.email || ""),
    };
  } catch (_error) {
    return null;
  }
}

function setCurrentUser(user, sessionToken = "") {
  state.currentUser = user || null;
  const nextSessionToken = String(sessionToken || "").trim();
  if (nextSessionToken) {
    setApiSessionToken(nextSessionToken);
    storeSessionToken(nextSessionToken);
  } else if (!user) {
    setApiSessionToken("");
    storeSessionToken("");
  }
  if (user) {
    storeRememberedUser(user);
  }
}

function clearCurrentUser() {
  resetSessionState(state);
  setCurrentUser(null);
  state.plants = [];
  state.selectedPlant = null;
  clearIntakePreview();
  clearDetailPreview();
  resetIntakeSuggestion(state);
  resetDetailEditorState(state);
}

async function loadAdminMetrics() {
  state.adminLoading = true;
  renderCurrentView();
  try {
    state.adminMetrics = await fetchAdminMetrics();
  } finally {
    state.adminLoading = false;
  }
}

function resetPurchaseDateInput() {
  if (elements.intakePurchaseDateInput) {
    elements.intakePurchaseDateInput.value = todayInputValue();
  }
}

function knownRooms() {
  return Array.from(
    new Set(
      state.plants
        .map((plant) => String(plant.location || "").trim())
        .filter(Boolean)
    )
  ).sort((left, right) => left.localeCompare(right));
}

function setPlantNameEditing(isEditing) {
  state.intakePlantNameEditing = isEditing;
  const displayName = state.intakePlantNameTouched && state.intakePlantName.trim()
    ? state.intakePlantName.trim()
    : state.intakeSuggestion.name;
  if (elements.suggestedNameEl) {
    elements.suggestedNameEl.textContent = displayName;
    elements.suggestedNameEl.hidden = isEditing;
  }
  if (elements.editPlantNameButton) {
    elements.editPlantNameButton.hidden = isEditing;
  }
  if (elements.plantNameInput) {
    elements.plantNameInput.hidden = !isEditing;
  }
  if (isEditing && elements.plantNameInput) {
    elements.plantNameInput.value = state.intakePlantName;
    queueMicrotask(() => {
      elements.plantNameInput.focus();
      elements.plantNameInput.select();
    });
  }
}

function intakeSignature() {
  const file = elements.intakePhotoInput?.files?.[0];
  if (!file) return "";
  return [file.name || "", String(file.size || 0), String(file.lastModified || 0)].join("|");
}

function revokeUrl(url) {
  if (url) {
    URL.revokeObjectURL(url);
  }
}

function clearIntakePreview() {
  revokeUrl(state.intakePreviewUrl);
  state.intakePreviewUrl = null;
}

function clearDetailPreview() {
  revokeUrl(state.detailPreviewUrl);
  state.detailPreviewUrl = null;
}

function setActiveTab() {
  if (!state.currentUser) {
    elements.tabBarEl.hidden = true;
    return;
  }
  elements.tabBarEl.hidden = false;
  elements.tabButtons.forEach((button) => {
    const route = button.getAttribute("data-route");
    if (route === "add") {
      button.textContent = t().tabs.add;
    }
    if (route === "garden") {
      button.textContent = t().tabs.garden;
    }
  });
  const activeRoute = state.route.name === "detail" || state.route.name === "checkin" || state.route.name === "chat" || state.route.name === "admin"
    ? "garden"
    : state.route.name;
  elements.tabButtons.forEach((button) => {
    const isActive = button.getAttribute("data-route") === activeRoute;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });
}

function renderLanguageOptions() {
  elements.languageButtons.forEach((button) => {
    const isActive = button.getAttribute("data-language") === state.language;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-pressed", isActive ? "true" : "false");
  });
}

function renderAddStaticCopy() {
  const copy = t().add;
  elements.addEyebrowEl.textContent = copy.eyebrow;
  elements.addTitleEl.textContent = copy.title;
  elements.intakeLocationLabelEl.textContent = copy.location;
  elements.intakeLocationInput.placeholder = copy.locationPlaceholder;
  elements.intakePurchaseDateLabelEl.textContent = copy.purchaseDate;
  document.getElementById("save-plant").textContent = copy.save;
}

function showView(name) {
  elements.authViewEl.hidden = name !== "auth";
  elements.gardenViewEl.hidden = name !== "garden";
  elements.adminViewEl.hidden = name !== "admin";
  elements.addViewEl.hidden = name !== "add";
  elements.detailViewEl.hidden = name !== "detail";
  elements.chatViewEl.hidden = name !== "chat";
}

function renderSessionBar() {
  const activeUser = state.currentUser;
  elements.sessionBarEl.hidden = !activeUser;
  if (!activeUser) {
    return;
  }
  const copy = t().session;
  const eyebrow = elements.sessionBarEl.querySelector(".eyebrow");
  if (eyebrow) {
    eyebrow.textContent = copy.eyebrow;
  }
  elements.sessionUserNameEl.textContent = state.language === "zh"
    ? `${activeUser.name}${copy.gardenSuffix}`
    : `${activeUser.name}'s ${copy.gardenSuffix}`;
  elements.sessionUserEmailEl.textContent = activeUser.email || "";
  if (elements.adminLink) {
    elements.adminLink.hidden = !state.isAdmin;
    elements.adminLink.textContent = copy.stats;
  }
  elements.switchProfileButton.textContent = copy.switch;
  elements.switchProfileButton.dataset.mode = "switch";
}

function renderAuthView() {
  const authCopy = t().auth;
  const title = state.authNeedsName
    ? (state.sessionClaimable ? authCopy.claimTitle : authCopy.createTitle)
    : authCopy.openTitle;
  const bodyCopy = state.authNeedsName
    ? (state.sessionClaimable
      ? authCopy.claimCopy
      : authCopy.createCopy)
    : authCopy.openCopy;
  const remembered = state.rememberedUser;

  elements.authEyebrowEl.textContent = authCopy.eyebrow;
  elements.authTitleEl.textContent = title;
  elements.authCopyEl.textContent = bodyCopy;
  elements.authNameLabelEl.textContent = authCopy.name;
  elements.authNameInput.placeholder = authCopy.namePlaceholder;
  elements.authEmailLabelEl.textContent = authCopy.email;
  elements.authEmailInput.placeholder = authCopy.emailPlaceholder;
  elements.authPasswordLabelEl.textContent = authCopy.password;
  elements.authPasswordInput.placeholder = authCopy.passwordPlaceholder;
  elements.authNameFieldEl.hidden = !state.authNeedsName;
  elements.authNameInput.required = state.authNeedsName;
  if (!state.authNeedsName) {
    elements.authNameInput.value = "";
  }
  elements.authSubmitButton.disabled = state.authSubmitting;
  elements.authSubmitButton.textContent = state.authSubmitting ? authCopy.opening : authCopy.continue;
  if (remembered && !elements.authEmailInput.value) {
    elements.authEmailInput.value = remembered.email;
  }
  renderLanguageOptions();
  renderSessionBar();
  elements.tabBarEl.hidden = true;
  showView("auth");
}

function openAddPhotoPicker() {
  elements.intakePhotoInput?.click();
}

function openCheckinPhotoPicker() {
  document.getElementById("checkin-photo")?.click();
}

async function appendThumbnail(payload, file) {
  const thumbnail = await createPhotoThumbnail(file);
  if (thumbnail) {
    payload.append("thumbnail", thumbnail);
  }
}

function handleStartEditDetailName() {
  state.detailDraftName = String(state.selectedPlant?.name || "");
  state.detailNameEditing = true;
  renderCurrentView();
}

function handleCancelEditDetailName() {
  state.detailDraftName = String(state.selectedPlant?.name || "");
  state.detailNameEditing = false;
  renderCurrentView();
}

function handleOpenPlant(plantId) {
  clearDetailPreview();
  state.detailWateringMonthOffset = 0;
  setRoute(`/plant/${encodeURIComponent(plantId)}`, syncRoute);
}

async function loadPlants() {
  state.plants = await fetchPlants();
}

async function loadPlantDetail(plantId) {
  state.selectedPlant = await fetchPlantDetail(plantId);
}

async function loadPlantChat(plantId, checkinId = "") {
  const data = await fetchPlantChat(plantId, checkinId);
  state.selectedPlant = data.plant;
  state.chatThread = data.thread;
  state.chatMessages = data.messages || [];
  state.chatFocusedCheckin = data.focused_checkin || null;
  state.chatSuggestedPrompts = data.suggested_prompts || [];
}

function handleBackToGarden() {
  setRoute("/garden", syncRoute);
}

async function handleRefreshAdmin() {
  if (!state.isAdmin || state.adminLoading) {
    return;
  }
  try {
    await loadAdminMetrics();
  } catch (error) {
    showToast(error.message || "Could not refresh stats");
  } finally {
    renderCurrentView();
  }
}

async function refreshSessionState() {
  const payload = await fetchSession();
  state.sessionClaimable = Boolean(payload.claimable_legacy_garden);
  state.isAdmin = Boolean(payload.is_admin);
  if (payload.user) {
    state.authNeedsName = false;
    setCurrentUser(payload.user);
    return payload.user;
  }
  setCurrentUser(null);
  state.isAdmin = false;
  return null;
}

async function bootstrapSession() {
  state.rememberedUser = readRememberedUser();
  setApiSessionToken(readStoredSessionToken());
  try {
    return await refreshSessionState();
  } catch (error) {
    state.currentUser = null;
    throw error;
  }
}

async function applyPlantUpdate(patch) {
  if (!state.selectedPlant) {
    throw new Error("Plant not found.");
  }
  const plant = await patchPlant(state.selectedPlant.id, patch);
  state.selectedPlant = plant;
  state.detailEditorPlantId = plant.id;
  state.detailDraftName = String(plant.name || "");
  await loadPlants();
}

async function saveDetailName() {
  if (!state.selectedPlant || state.detailNameSaving) {
    return;
  }

  const nextName = state.detailDraftName.trim();
  if (!nextName) {
    showToast("Plant name cannot be empty");
    return;
  }
  if (nextName === state.selectedPlant.name) {
    state.detailNameEditing = false;
    renderCurrentView();
    return;
  }

  state.detailNameSaving = true;
  renderCurrentView();
  try {
    await applyPlantUpdate({ name: nextName });
    state.detailNameEditing = false;
    showToast("Plant name updated");
  } catch (error) {
    showToast(error.message || "Could not update plant name");
  } finally {
    state.detailNameSaving = false;
    renderCurrentView();
  }
}

function handleSwitchProfile() {
  clearCurrentUser();
  if (elements.authForm) {
    elements.authForm.reset();
  }
  if (state.rememberedUser?.email && elements.authEmailInput) {
    elements.authEmailInput.value = state.rememberedUser.email;
  }
  showToast("Choose a garden profile");
  renderCurrentView();
}

async function handleResumeRememberedGarden() {
  const remembered = state.rememberedUser;
  if (!remembered?.id) {
    return;
  }

  const sessionToken = readStoredSessionToken();
  if (sessionToken) {
    state.authSubmitting = true;
    setApiSessionToken(sessionToken);
    renderCurrentView();
    try {
      const user = await refreshSessionState();
      if (user) {
        await loadPlants();
        state.selectedPlant = null;
        resetPurchaseDateInput();
        showToast("Garden opened");
        setRoute("/garden", syncRoute);
        return;
      }
      showToast("Session expired. Enter your password.");
    } catch (_error) {
      showToast("Could not reuse the saved session. Enter your password.");
    } finally {
      state.authSubmitting = false;
      renderCurrentView();
    }
  }

  if (elements.authEmailInput) {
    elements.authEmailInput.value = remembered.email;
  }
  if (elements.authPasswordInput) {
    elements.authPasswordInput.value = "";
  }
  showToast("Enter your password to continue");
  renderCurrentView();
  queueMicrotask(() => elements.authPasswordInput?.focus());
}

async function handleDeletePlant() {
  const route = state.route;
  if ((route.name !== "detail" && route.name !== "checkin") || !route.plantId || !state.selectedPlant) {
    return;
  }

  const confirmed = window.confirm(`Delete ${state.selectedPlant.name}? This cannot be undone.`);
  if (!confirmed) {
    return;
  }

  try {
    await deletePlantRequest(route.plantId);
    clearDetailPreview();
    await loadPlants();
    state.selectedPlant = null;
    showToast("Plant deleted");
    setRoute("/garden", syncRoute);
  } catch (error) {
    showToast(error.message || "Could not delete plant");
  }
}

async function handleDeleteCheckin(checkinId) {
  if (!state.selectedPlant) {
    return;
  }

  const confirmed = window.confirm("Delete this diagnosis? This cannot be undone.");
  if (!confirmed) {
    return;
  }

  try {
    await deleteCheckinRequest(checkinId);
    await loadPlants();
    await loadPlantDetail(state.selectedPlant.id);
    renderCurrentView();
    showToast("Diagnosis deleted");
  } catch (error) {
    showToast(error.message || "Could not delete diagnosis");
  }
}

function syncWateringDom() {
  if (!state.selectedPlant || state.route.name !== "detail") {
    return;
  }

  const wateredDates = new Set(
    Array.isArray(state.selectedPlant.watering_dates)
      ? state.selectedPlant.watering_dates.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
  );
  elements.detailViewEl.querySelectorAll("[data-watering-date]").forEach((button) => {
    const dateKey = String(button.getAttribute("data-watering-date") || "").trim();
    const isWatered = wateredDates.has(dateKey);
    const isToday = dateKey === todayInputValue();
    button.classList.toggle("is-watered", isWatered);
    button.setAttribute("aria-pressed", isWatered ? "true" : "false");
    button.setAttribute(
      "aria-label",
      `${dateKey}${isWatered ? ", watered" : ", not watered"}${isToday ? ", today" : ""}`,
    );
  });

  const heading = elements.detailViewEl.querySelector(".watering-head h3");
  if (!heading) {
    return;
  }
  const wateredToday = wateredDates.has(todayInputValue());
  const lastWateredLabel = state.selectedPlant.last_watered_on
    ? formatDateOnly(state.selectedPlant.last_watered_on)
    : "";
  heading.textContent = wateredToday
    ? "Watered today"
    : lastWateredLabel
      ? `Last watered ${lastWateredLabel}`
      : "Not watered yet";
}

async function handleToggleWateringDate(wateredOn) {
  if (!state.selectedPlant) {
    return;
  }

  const plantId = state.selectedPlant.id;
  const targetDate = String(wateredOn || "").trim();
  if (!targetDate) {
    return;
  }
  const wateredDates = new Set(
    Array.isArray(state.selectedPlant.watering_dates)
      ? state.selectedPlant.watering_dates.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
  );
  const alreadyWatered = wateredDates.has(targetDate);
  const previousPlant = state.selectedPlant;
  if (alreadyWatered) {
    wateredDates.delete(targetDate);
  } else {
    wateredDates.add(targetDate);
  }
  const optimisticDates = Array.from(wateredDates).sort().reverse();
  state.selectedPlant = {
    ...state.selectedPlant,
    watering_dates: optimisticDates,
    watered_today: wateredDates.has(todayInputValue()),
    last_watered_on: optimisticDates[0] || null,
  };
  syncWateringDom();

  try {
    const data = await setWateringRequest(plantId, {
      watered_on: targetDate,
      watered: !alreadyWatered,
    });
    state.selectedPlant = data.plant || state.selectedPlant;
    syncWateringDom();
    showToast(alreadyWatered ? "Watering removed" : "Watering saved");
  } catch (error) {
    state.selectedPlant = previousPlant;
    syncWateringDom();
    showToast(error.message || "Could not update watering");
  }
}

function handlePreviousWateringMonth() {
  state.detailWateringMonthOffset -= 1;
  renderCurrentView();
}

function handleNextWateringMonth() {
  state.detailWateringMonthOffset += 1;
  renderCurrentView();
}

async function fetchIntakeSuggestion(signature) {
  const file = elements.intakePhotoInput?.files?.[0];
  if (!file) {
    resetIntakeSuggestion(state);
    renderCurrentView();
    return;
  }

  const requestId = ++state.intakeSuggestionRequestId;
  state.intakeSuggestionLoading = true;
  renderCurrentView();

  const payload = new FormData();
  payload.append("photo", file);
  await appendThumbnail(payload, file);

  try {
    const data = await requestPlantIdentityPreview(payload);
    if (requestId !== state.intakeSuggestionRequestId) {
      return;
    }
    state.intakeSuggestion = normalizeSuggestion(data.suggestion || {});
    state.intakeDiagnosis = normalizeDiagnosis(data.diagnosis);
    state.intakeTip = normalizeTip(data.tip);
    state.intakeUploadToken = String(data.upload_token || "").trim();
    state.intakeSuggestionSignature = signature;
    syncIntakePlantNameFromSuggestion(state, state.intakeSuggestion);
  } catch (error) {
    if (requestId !== state.intakeSuggestionRequestId) {
      return;
    }
    state.intakeSuggestion = normalizeSuggestion({
      source: "heuristic",
      caption: error.message || "We could not analyze that photo just yet.",
    });
    state.intakeDiagnosis = null;
    state.intakeTip = null;
    state.intakeUploadToken = "";
    state.intakeSuggestionSignature = signature;
  } finally {
    if (requestId === state.intakeSuggestionRequestId) {
      state.intakeSuggestionLoading = false;
      renderCurrentView();
    }
  }
}

function handleIdentifyPlantClick() {
  const signature = intakeSignature();
  if (!signature) {
    showToast(t().toast.addPhotoFirst);
    return;
  }
  void fetchIntakeSuggestion(signature);
}

function renderCurrentView() {
  if (!state.currentUser) {
    renderAuthView();
    return;
  }

  renderSessionBar();
  setActiveTab();
  if (state.route.name === "add") {
    showView("add");
    renderAddStaticCopy();
    renderAddView({
      state,
      elements,
      intakeSignature,
      knownRooms,
      setPlantNameEditing,
      syncIntakePlantNameFromSuggestion: (suggestion) =>
        syncIntakePlantNameFromSuggestion(state, suggestion),
      onOpenPhotoPicker: openAddPhotoPicker,
      t: t(),
    });
    return;
  }

  if (state.route.name === "garden") {
    showView("garden");
    renderGarden({
      state,
      gardenViewEl: elements.gardenViewEl,
      onOpenPlant: handleOpenPlant,
      t: t(),
    });
    return;
  }

  if (state.route.name === "admin") {
    showView("admin");
    renderAdminDashboard({
      state,
      adminViewEl: elements.adminViewEl,
      onRefreshAdmin: handleRefreshAdmin,
      onBackToGarden: handleBackToGarden,
    });
    return;
  }

  if (state.route.name === "chat") {
    showView("chat");
    renderChatView({
      state,
      chatViewEl: elements.chatViewEl,
      actions: {
        onChatDraftInput: (value) => {
          state.chatDraft = value;
        },
        onChatSubmit: handleChatSubmit,
        onSendChatPrompt: handleSendChatPrompt,
      },
    });
    return;
  }

  showView("detail");
  if (state.route.name === "checkin") {
    renderCheckinView({
      state,
      detailViewEl: elements.detailViewEl,
      actions: {
        onDetailPhotoPreview: handleDetailPhotoPreview,
        onOpenCheckinPhotoPicker: openCheckinPhotoPicker,
        onCheckinSubmit: handleCheckinSubmit,
      },
    });
    return;
  }

  renderDetail({
    state,
    detailViewEl: elements.detailViewEl,
    syncDetailEditorState: () => syncDetailEditorState(state),
    actions: {
      onStartEditName: handleStartEditDetailName,
      onDetailNameInput: (value) => {
        state.detailDraftName = value;
      },
      onSaveDetailName: saveDetailName,
      onCancelEditName: handleCancelEditDetailName,
      onToggleWateringDate: handleToggleWateringDate,
      onPreviousWateringMonth: handlePreviousWateringMonth,
      onNextWateringMonth: handleNextWateringMonth,
      onDeletePlant: handleDeletePlant,
      onDeleteCheckin: handleDeleteCheckin,
    },
  });
}

async function syncRoute() {
  const route = routeFromHash();
  state.route = route;
  if (!state.currentUser) {
    renderCurrentView();
    return;
  }
  await loadPlants();

  if (route.name === "admin") {
    resetChatState(state);
    state.selectedPlant = null;
    if (!state.isAdmin) {
      showToast("Admin access required");
      setRoute("/garden", syncRoute);
      return;
    }
    try {
      await loadAdminMetrics();
    } catch (error) {
      showToast(error.message || "Could not load stats");
    }
  } else if (route.name === "detail" || route.name === "checkin") {
    resetChatState(state);
    const exists = state.plants.some((plant) => plant.id === route.plantId);
    if (!exists) {
      state.selectedPlant = null;
      showToast("That plant could not be found");
      setRoute("/garden", syncRoute);
      return;
    }
    if (state.selectedPlant?.id !== route.plantId) {
      state.detailWateringMonthOffset = 0;
    }
    await loadPlantDetail(route.plantId);
  } else if (route.name === "chat") {
    const exists = state.plants.some((plant) => plant.id === route.plantId);
    if (!exists) {
      state.selectedPlant = null;
      resetChatState(state);
      showToast("That plant could not be found");
      setRoute("/garden", syncRoute);
      return;
    }
    await loadPlantChat(route.plantId, route.checkinId || "");
  } else {
    state.selectedPlant = null;
    resetChatState(state);
  }

  renderCurrentView();
}

async function handleAddPlantSubmit(event) {
  event.preventDefault();
  const photoFile = elements.intakePhotoInput?.files?.[0] || null;
  const locationValue = elements.intakeLocationInput?.value?.trim() || "";
  const customNameValue = elements.plantNameInput?.value?.trim() || "";

  if (!photoFile) {
    showToast(t().toast.takePhotoFirst);
    return;
  }

  const payload = new FormData();
  payload.append("client_created_at", localDateTimeValue());
  if (locationValue) {
    payload.append("location", locationValue);
  }
  const activeSuggestion = state.intakeSuggestion;
  const hasFreshSuggestion = state.intakeSuggestionSignature === intakeSignature();
  const activeDiagnosis = hasFreshSuggestion ? state.intakeDiagnosis : null;
  const activeUploadToken = hasFreshSuggestion ? state.intakeUploadToken : "";
  if (!hasFreshSuggestion) {
    showToast(t().toast.identifyFirst);
    return;
  }
  const resolvedName = customNameValue || (hasFreshSuggestion ? activeSuggestion?.name || "" : "");
  if (!resolvedName || isUnknownSuggestionName(resolvedName)) {
    setPlantNameEditing(true);
    showToast(t().toast.namePlant);
    return;
  }
  if (activeUploadToken) {
    payload.append("upload_token", activeUploadToken);
    await appendThumbnail(payload, photoFile);
  } else {
    showToast(t().toast.reidentify);
    return;
  }
  payload.append("name", resolvedName);
  if (activeSuggestion?.species && state.intakeSuggestionSignature === intakeSignature()) {
    payload.append("species", activeSuggestion.species);
  }
  if (activeSuggestion?.chinese_name && state.intakeSuggestionSignature === intakeSignature()) {
    payload.append("chinese_name", activeSuggestion.chinese_name);
  }
  if (activeDiagnosis) {
    payload.append("diagnosis_payload", JSON.stringify(activeDiagnosis));
  }
  if (state.intakeTip) {
    payload.append("tip_payload", JSON.stringify(state.intakeTip));
  }

  const saveButton = document.getElementById("save-plant");
  saveButton.disabled = true;
  saveButton.textContent = t().add.saving;

  try {
    const data = await createPlantRequest(payload);

    elements.addPlantForm.reset();
    clearIntakePreview();
    resetIntakeSuggestion(state);
    resetPurchaseDateInput();
    renderCurrentView();
    showToast(`${t().toast.savedPrefix} ${data.plant.name}`);
    setRoute(`/plant/${encodeURIComponent(data.plant.id)}`, syncRoute);
  } catch (error) {
    showToast(error.message || t().toast.saveError);
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = t().add.save;
  }
}

async function handleCheckinSubmit(event) {
  event.preventDefault();
  const route = state.route;
  if (route.name !== "checkin" || !route.plantId) return;

  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit']");
  const noteValue = form.querySelector("#checkin-note")?.value?.trim() || "";
  const photoFile = form.querySelector("#checkin-photo")?.files?.[0] || null;

  if (!noteValue && !photoFile) {
    showToast("Add a photo or a short note first");
    return;
  }

  const payload = new FormData();
  if (photoFile) {
    payload.append("photo", photoFile);
    await appendThumbnail(payload, photoFile);
  }
  if (noteValue) {
    payload.append("note", noteValue);
  }
  payload.append("client_created_at", localDateTimeValue());

  submitButton.disabled = true;
  submitButton.textContent = "Diagnosing...";

  try {
    await createCheckinRequest(route.plantId, payload);

    clearDetailPreview();
    showToast("Check-in saved");
    setRoute(`/plant/${encodeURIComponent(route.plantId)}`, syncRoute);
  } catch (error) {
    showToast(error.message || "Could not save check-in");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Diagnose and save";
  }
}

async function sendChatMessage(body) {
  const route = state.route;
  if (route.name !== "chat" || !route.plantId || !state.selectedPlant || state.chatSending) {
    return;
  }

  const trimmedBody = String(body || "").trim();
  if (!trimmedBody) {
    showToast("Add a follow-up question first");
    return;
  }

  state.chatSending = true;
  renderCurrentView();

  try {
    const data = await createPlantChatMessageRequest(route.plantId, {
      body: trimmedBody,
      checkin_id: state.chatFocusedCheckin?.id || route.checkinId || undefined,
    });
    state.chatThread = data.thread || state.chatThread;
    state.chatFocusedCheckin = data.focused_checkin || state.chatFocusedCheckin;
    state.chatMessages = [
      ...(state.chatMessages || []),
      data.user_message,
      data.assistant_message,
    ].filter(Boolean);
    state.chatDraft = "";
    renderCurrentView();
  } catch (error) {
    showToast(error.message || "Could not send follow-up");
  } finally {
    state.chatSending = false;
    renderCurrentView();
  }
}

async function handleChatSubmit(event) {
  event.preventDefault();
  await sendChatMessage(state.chatDraft);
}

async function handleSendChatPrompt(prompt) {
  state.chatDraft = String(prompt || "").trim();
  renderCurrentView();
  await sendChatMessage(state.chatDraft);
}

async function handleAuthSubmit(event) {
  event.preventDefault();
  const name = elements.authNameInput?.value?.trim() || "";
  const email = elements.authEmailInput?.value?.trim() || "";
  const password = elements.authPasswordInput?.value || "";
  if (!email) {
    showToast(t().toast.authEmail);
    return;
  }
  if (password.length < 8) {
    showToast(t().toast.authPassword);
    return;
  }
  if (state.authNeedsName && !name) {
    showToast(t().toast.authName);
    return;
  }

  state.authSubmitting = true;
  renderCurrentView();
  try {
    const payload = await createSessionRequest({
      name: state.authNeedsName ? name : "",
      email,
      password,
    });
    setCurrentUser(payload.user || null, payload.session_token || "");
    state.isAdmin = Boolean(payload.is_admin);
    state.sessionClaimable = Boolean(payload.claimable_legacy_garden);
    state.authNeedsName = false;
    await loadPlants();
    state.selectedPlant = null;
    resetPurchaseDateInput();
    renderCurrentView();
    const welcomeMessage = payload.password_was_set
      ? "Garden secured"
      : `Welcome, ${state.currentUser?.name || "friend"}`;
    showToast(payload.claimed_legacy_garden ? "Garden claimed" : welcomeMessage);
    setRoute("/garden", syncRoute);
  } catch (error) {
    if ((error.message || "").includes("Add your name to create a new garden.")) {
      state.authNeedsName = true;
      renderCurrentView();
      queueMicrotask(() => elements.authNameInput?.focus());
    }
    showToast(error.message || "Could not open your garden");
  } finally {
    state.authSubmitting = false;
    renderCurrentView();
  }
}

function handleIntakePhotoChange(event) {
  clearIntakePreview();
  const file = event.target.files?.[0];
  if (file) {
    state.intakePreviewUrl = URL.createObjectURL(file);
  }
  resetIntakeSuggestion(state);
  renderCurrentView();
}

function handleDetailPhotoPreview(event) {
  clearDetailPreview();
  const file = event.target.files?.[0];
  if (!file) {
    updateDetailPreviewSlot({
      state,
      onOpenCheckinPhotoPicker: openCheckinPhotoPicker,
    });
    return;
  }
  state.detailPreviewUrl = URL.createObjectURL(file);
  updateDetailPreviewSlot({
    state,
    onOpenCheckinPhotoPicker: openCheckinPhotoPicker,
  });
}

function bindStaticEvents() {
  elements.languageButtons.forEach((button) => {
    button.addEventListener("click", () => {
      setLanguage(button.getAttribute("data-language"));
      renderCurrentView();
    });
  });
  elements.authForm?.addEventListener("submit", handleAuthSubmit);
  elements.switchProfileButton?.addEventListener("click", () => {
    if (elements.switchProfileButton.dataset.mode === "resume") {
      void handleResumeRememberedGarden();
      return;
    }
    handleSwitchProfile();
  });
  elements.authEmailInput?.addEventListener("input", () => {
    if (state.authNeedsName) {
      state.authNeedsName = false;
      renderCurrentView();
    }
  });
  elements.tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const route = button.getAttribute("data-route");
      if (!route) return;
      clearDetailPreview();
      setRoute(`/${route}`, syncRoute);
    });
  });

  elements.addPlantForm.addEventListener("submit", handleAddPlantSubmit);
  elements.intakePhotoInput?.addEventListener("change", handleIntakePhotoChange);
  elements.plantNameInput?.addEventListener("input", () => {
    state.intakePlantName = elements.plantNameInput.value;
    state.intakePlantNameTouched = true;
  });
  elements.plantNameInput?.addEventListener("blur", () => {
    state.intakePlantName = elements.plantNameInput.value.trim();
    if (state.intakePlantName) {
      setPlantNameEditing(false);
    }
  });
  elements.plantNameInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      state.intakePlantName = elements.plantNameInput.value.trim();
      if (state.intakePlantName) {
        setPlantNameEditing(false);
      }
    }
    if (event.key === "Escape") {
      event.preventDefault();
      elements.plantNameInput.value = state.intakePlantName;
      setPlantNameEditing(false);
    }
  });
  elements.editPlantNameButton?.addEventListener("click", () => {
    setPlantNameEditing(true);
  });
  elements.identifyPlantButton?.addEventListener("click", handleIdentifyPlantClick);
  window.addEventListener("hashchange", syncRoute);
}

async function boot() {
  setLanguage(readStoredLanguage());
  bindStaticEvents();
  resetPurchaseDateInput();
  void registerServiceWorker();

  if (!window.location.hash || window.location.hash === "#/overview") {
    window.location.hash = "#/add";
  }

  resetIntakeSuggestion(state);
  resetDetailEditorState(state);

  try {
    await bootstrapSession();
    await syncRoute();
  } catch (error) {
    elements.addViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Something went wrong</p>
        <h2>We could not load your garden</h2>
        <p class="empty-copy">${escapeHtml(error.message || "Please try again.")}</p>
      </div>
    `;
    showView("add");
  }
}

boot();
