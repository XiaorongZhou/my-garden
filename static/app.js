const gardenViewEl = document.getElementById("garden-view");
const addViewEl = document.getElementById("add-view");
const detailViewEl = document.getElementById("detail-view");
const addPlantForm = document.getElementById("add-plant-form");
const toastEl = document.getElementById("toast");
const tabButtons = Array.from(document.querySelectorAll(".tab-button"));
const intakePhotoInput = document.getElementById("intake-photo");
const intakeLocationInput = document.getElementById("plant-location");
const intakePurchaseDateInput = document.getElementById("plant-purchase-date");
const roomOptionsEl = document.getElementById("room-options");
const intakePreviewEl = document.getElementById("intake-photo-preview");
const suggestionCardEl = document.getElementById("suggestion-card");
const suggestedNameEl = document.getElementById("suggested-name");
const suggestedSpeciesEl = document.getElementById("suggested-species");
const suggestedMetaEl = document.getElementById("suggested-meta");
const suggestedCaptionEl = document.getElementById("suggested-caption");
const suggestedDiagnosisEl = document.getElementById("suggested-diagnosis");
const suggestedDiagnosisStatusEl = document.getElementById("suggested-diagnosis-status");
const suggestedDiagnosisTitleEl = document.getElementById("suggested-diagnosis-title");
const suggestedDiagnosisSummaryEl = document.getElementById("suggested-diagnosis-summary");
const plantNameInput = document.getElementById("plant-name");
const editPlantNameButton = document.getElementById("edit-plant-name");
const identifyPlantButton = document.getElementById("identify-plant");

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

function defaultSuggestion() {
  return {
    name: "Unknown Houseplant",
    species: "Unknown houseplant",
    confidence: "low",
    source: "idle",
    caption: "Add a photo, then tap Identify plant.",
  };
}

const state = {
  plants: [],
  selectedPlant: null,
  route: { name: "add" },
  intakePreviewUrl: null,
  detailPreviewUrl: null,
  intakeSuggestion: defaultSuggestion(),
  intakeDiagnosis: null,
  intakeUploadToken: "",
  intakeSuggestionLoading: false,
  intakeSuggestionRequestId: 0,
  intakeSuggestionSignature: "",
  intakePlantName: "",
  intakePlantNameTouched: false,
  intakePlantNameEditing: false,
  toastTimer: null,
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function showToast(message) {
  toastEl.textContent = message;
  toastEl.classList.add("show");
  if (state.toastTimer) {
    clearTimeout(state.toastTimer);
  }
  state.toastTimer = setTimeout(() => {
    toastEl.classList.remove("show");
  }, 1800);
}

function initialsFor(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function todayInputValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function resetPurchaseDateInput() {
  if (intakePurchaseDateInput) {
    intakePurchaseDateInput.value = todayInputValue();
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

function statusLabel(status) {
  if (status === "thriving") return "Thriving";
  if (status === "needs_care") return "Needs care";
  return "Watch";
}

function fallbackSummary(checkin) {
  if (!checkin) return "";
  const summary = String(checkin.diagnosis_summary || "").trim();
  if (summary) return summary;
  if (!String(checkin.note || "").trim()) {
    return "No symptom note yet. Add one quick observation next time so the read can be specific.";
  }
  return "";
}

function historyDisclosureMarkup(checkin, plant) {
  const diagnosis = fallbackSummary(checkin);
  const ownerNote = String(checkin.note || "").trim();
  return `
    <details class="history-card history-disclosure">
      <summary class="history-summary">
        <div class="history-photo">
          ${photoMarkup(checkin.photo_url, `${plant.name} check-in`, initialsFor(plant.name))}
        </div>
        <div class="history-summary-main">
          <div class="history-title">
            <h3>${escapeHtml(checkin.diagnosis_title)}</h3>
            <span class="status-pill ${escapeHtml(checkin.health_status)}">${escapeHtml(statusLabel(checkin.health_status))}</span>
          </div>
          <p class="history-meta">${escapeHtml(formatDate(checkin.created_at))}</p>
        </div>
        <span class="history-chevron" aria-hidden="true">⌄</span>
      </summary>
      <div class="history-panel">
        ${
          diagnosis
            ? `
              <div class="history-panel-block">
                <p class="history-panel-label">Saved diagnosis</p>
                <p class="history-copy">${escapeHtml(diagnosis)}</p>
              </div>
            `
            : ""
        }
        ${
          ownerNote
            ? `
              <div class="history-panel-block">
                <p class="history-panel-label">What you noted</p>
                <p class="history-copy">${escapeHtml(ownerNote)}</p>
              </div>
            `
            : ""
        }
      </div>
    </details>
  `;
}

function photoMarkup(url, alt, fallback) {
  if (url) {
    return `<img src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" />`;
  }
  return `<div class="empty-photo">${escapeHtml(fallback)}</div>`;
}

function placeholderPhotoMarkup(buttonId) {
  return `
    <div class="intake-placeholder intake-placeholder-action">
      <p class="eyebrow">Photo preview</p>
      <button id="${escapeHtml(buttonId)}" class="ghost-button intake-placeholder-button icon-photo-button" type="button" aria-label="Add photo">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M8 6.5 9.4 4h5.2L16 6.5h2.2A2.8 2.8 0 0 1 21 9.3v7.4a2.8 2.8 0 0 1-2.8 2.8H5.8A2.8 2.8 0 0 1 3 16.7V9.3a2.8 2.8 0 0 1 2.8-2.8Zm4 3.1a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0 1.8a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4Z"></path>
        </svg>
      </button>
    </div>
  `;
}

function resetIntakeSuggestion() {
  state.intakeSuggestion = defaultSuggestion();
  state.intakeDiagnosis = null;
  state.intakeUploadToken = "";
  state.intakeSuggestionLoading = false;
  state.intakeSuggestionSignature = "";
  state.intakePlantName = "";
  state.intakePlantNameTouched = false;
  state.intakePlantNameEditing = false;
}

function isUnknownSuggestionName(value) {
  return String(value || "").trim().toLowerCase() === "unknown houseplant";
}

function hasUsefulSpeciesLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return Boolean(normalized) && ![
    "unknown houseplant",
    "photo attached",
    "identifying your plant",
  ].includes(normalized);
}

function syncIntakePlantNameFromSuggestion(suggestion) {
  if (state.intakePlantNameTouched) {
    return;
  }
  state.intakePlantName = isUnknownSuggestionName(suggestion?.name) ? "" : String(suggestion?.name || "").trim();
}

function setPlantNameEditing(isEditing) {
  state.intakePlantNameEditing = isEditing;
  const displayName = state.intakePlantNameTouched && state.intakePlantName.trim()
    ? state.intakePlantName.trim()
    : state.intakeSuggestion.name;
  if (suggestedNameEl) {
    suggestedNameEl.textContent = displayName;
    suggestedNameEl.hidden = isEditing;
  }
  if (editPlantNameButton) {
    editPlantNameButton.hidden = isEditing;
  }
  if (plantNameInput) {
    plantNameInput.hidden = !isEditing;
  }
  if (isEditing && plantNameInput) {
    plantNameInput.value = state.intakePlantName;
    queueMicrotask(() => {
      plantNameInput.focus();
      plantNameInput.select();
    });
  }
}

function intakeSignature() {
  const file = intakePhotoInput?.files?.[0];
  if (!file) return "";
  return [file.name || "", String(file.size || 0), String(file.lastModified || 0)].join("|");
}

function suggestionMetaLabel(suggestion) {
  if (state.intakeSuggestionLoading) {
    return "Analyzing photo";
  }
  if (suggestion.source === "openai") {
    const confidence = suggestion.confidence ? ` · ${suggestion.confidence} confidence` : "";
    return `Photo ID${confidence}`;
  }
  if (suggestion.source === "heuristic") {
    return "Backup guess";
  }
  if (suggestion.source === "ready") {
    return "Ready to identify";
  }
  return "Suggested plant";
}

function normalizeSuggestion(payload) {
  const base = defaultSuggestion();
  return {
    ...base,
    ...payload,
    name: payload?.name || base.name,
    species: payload?.species || base.species,
    caption: payload?.caption || base.caption,
    confidence: payload?.confidence || base.confidence,
    source: payload?.source || base.source,
  };
}

function normalizeDiagnosis(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const healthStatus = ["thriving", "watch", "needs_care"].includes(String(payload.health_status || "").trim())
    ? String(payload.health_status).trim()
    : "watch";
  const diagnosisTitle = String(payload.diagnosis_title || "").trim();
  const diagnosisSummary = String(payload.diagnosis_summary || "").trim();
  const careSteps = Array.isArray(payload.care_steps)
    ? payload.care_steps.map((step) => String(step || "").trim()).filter(Boolean).slice(0, 3)
    : [];
  if (!diagnosisTitle && !diagnosisSummary && !careSteps.length) {
    return null;
  }
  return {
    health_status: healthStatus,
    diagnosis_title: diagnosisTitle || "Nothing alarming stands out yet",
    diagnosis_summary: diagnosisSummary,
    care_steps: careSteps,
  };
}

function routeFromHash() {
  const raw = window.location.hash.replace(/^#\/?/, "").trim();
  if (!raw || raw === "overview" || raw === "add") {
    return { name: "add" };
  }
  if (raw === "garden") {
    return { name: "garden" };
  }
  const checkinMatch = raw.match(/^plant\/(.+)\/checkin$/);
  if (checkinMatch) {
    return { name: "checkin", plantId: decodeURIComponent(checkinMatch[1]) };
  }
  if (raw.startsWith("plant/")) {
    const plantId = decodeURIComponent(raw.slice("plant/".length));
    return { name: "detail", plantId };
  }
  return { name: "add" };
}

function setRoute(nextHash) {
  const normalized = nextHash.startsWith("#") ? nextHash : `#${nextHash}`;
  if (window.location.hash === normalized) {
    syncRoute();
    return;
  }
  window.location.hash = normalized;
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
  const activeRoute = state.route.name === "detail" || state.route.name === "checkin" ? "garden" : state.route.name;
  tabButtons.forEach((button) => {
    const isActive = button.getAttribute("data-route") === activeRoute;
    button.classList.toggle("active", isActive);
    button.setAttribute("aria-current", isActive ? "page" : "false");
  });
}

function showView(name) {
  gardenViewEl.hidden = name !== "garden";
  addViewEl.hidden = name !== "add";
  detailViewEl.hidden = name !== "detail";
}

function renderAddView() {
  const file = intakePhotoInput?.files?.[0] || null;
  const currentSignature = intakeSignature();
  const suggestion = state.intakeSuggestionLoading
    ? {
        name: "Looking closely...",
        species: "Identifying your plant",
        caption: "We’re identifying the plant and drafting a first read before you save.",
        confidence: "",
        source: "loading",
      }
    : file && state.intakeSuggestionSignature !== currentSignature
      ? {
          name: "Ready when you are",
          species: "Photo attached",
          caption: "Tap Identify plant to preview the plant name and first read before saving.",
          confidence: "",
          source: "ready",
        }
      : state.intakeSuggestion;
  const diagnosis = state.intakeSuggestionLoading || state.intakeSuggestionSignature !== currentSignature
    ? null
    : state.intakeDiagnosis;

  const displayName = state.intakePlantNameTouched && state.intakePlantName.trim()
    ? state.intakePlantName.trim()
    : suggestion.name;

  suggestedNameEl.textContent = displayName;
  suggestedSpeciesEl.hidden = !hasUsefulSpeciesLabel(suggestion.species);
  suggestedSpeciesEl.textContent = hasUsefulSpeciesLabel(suggestion.species) ? suggestion.species : "";
  suggestedMetaEl.textContent = suggestionMetaLabel(suggestion);
  suggestedCaptionEl.textContent = suggestion.caption;
  if (suggestedDiagnosisEl) {
    suggestedDiagnosisEl.hidden = !diagnosis;
  }
  if (diagnosis) {
    suggestedDiagnosisStatusEl.className = `status-pill ${escapeHtml(diagnosis.health_status)}`;
    suggestedDiagnosisStatusEl.textContent = statusLabel(diagnosis.health_status);
    suggestedDiagnosisTitleEl.textContent = diagnosis.diagnosis_title;
    suggestedDiagnosisSummaryEl.textContent = diagnosis.diagnosis_summary || "Initial read saved and ready to use when you save this plant.";
  }
  syncIntakePlantNameFromSuggestion(suggestion);
  if (plantNameInput) {
    plantNameInput.value = state.intakePlantName;
    plantNameInput.placeholder = isUnknownSuggestionName(suggestion.name)
      ? "Give this plant a name before saving"
      : "Edit the plant name before saving";
  }
  setPlantNameEditing(state.intakePlantNameEditing);

  intakePreviewEl.innerHTML = state.intakePreviewUrl
    ? `<div class="preview-image"><img src="${escapeHtml(state.intakePreviewUrl)}" alt="Preview of your new plant photo" /></div>`
    : placeholderPhotoMarkup("empty-add-photo");

  if (identifyPlantButton) {
    identifyPlantButton.disabled = !file || state.intakeSuggestionLoading;
    identifyPlantButton.textContent = state.intakeSuggestionLoading
      ? "Identifying..."
      : file && state.intakeSuggestionSignature === currentSignature
        ? "Re-identify plant"
        : "Identify plant";
  }

  if (suggestionCardEl) {
    suggestionCardEl.hidden = !file;
  }

  if (roomOptionsEl) {
    roomOptionsEl.innerHTML = knownRooms()
      .map((room) => `<option value="${escapeHtml(room)}"></option>`)
      .join("");
  }

  document.getElementById("empty-add-photo")?.addEventListener("click", () => {
    intakePhotoInput?.click();
  });
}

function renderGarden() {
  if (!state.plants.length) {
    gardenViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">No plants yet</p>
        <h2>Start with the camera</h2>
        <p class="empty-copy">Use the Add Plant tab to snap a photo, save the plant, and create its first diagnosis.</p>
      </div>
    `;
    return;
  }

  const rows = state.plants
    .map((plant) => {
      const status = plant.latest_status || "watch";
      return `
        <button class="garden-row" type="button" data-open-plant="${escapeHtml(plant.id)}">
          <div class="garden-row-thumb">
            ${photoMarkup(plant.photo_url, `${plant.name} thumbnail`, initialsFor(plant.name))}
          </div>
          <div class="garden-row-main">
            <div class="garden-row-head">
              <h3>${escapeHtml(plant.name)}</h3>
              <span class="status-pill ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>
            </div>
            <p class="garden-row-meta">${escapeHtml(plant.species)} · ${escapeHtml(plant.location || "Home")}</p>
            <p class="garden-row-summary">${escapeHtml(plant.latest_summary || plant.latest_title || "No diagnosis yet. Start with a photo check-in.")}</p>
          </div>
          <span class="garden-row-chevron" aria-hidden="true">›</span>
        </button>
      `;
    })
    .join("");

  gardenViewEl.innerHTML = `
    <div class="panel">
      <div class="section-heading">
        <div>
          <p class="eyebrow">Your garden</p>
          <h2>Plant list</h2>
        </div>
        <p class="section-note">${escapeHtml(String(state.plants.length))} plants</p>
      </div>
      <div class="garden-list">${rows}</div>
    </div>
  `;

  bindDynamicRouteLinks(gardenViewEl);
}

function renderDetail() {
  const plant = state.selectedPlant;
  if (!plant) {
    detailViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Plant not found</p>
        <h2>Let’s head back to your garden</h2>
        <a class="ghost-button link-button" href="#/garden">Back to list</a>
      </div>
    `;
    return;
  }

  const latest = plant.latest_checkin;
  const historyMarkup = plant.checkins.length
    ? plant.checkins
        .map((checkin) => historyDisclosureMarkup(checkin, plant))
        .join("")
    : `
      <div class="empty-card">
        <h3>No check-ins yet</h3>
        <p class="empty-copy">Open a check-in when you want to save the first photo and diagnosis for this plant.</p>
      </div>
    `;

  detailViewEl.innerHTML = `
    <div class="detail-stack">
      <div class="detail-topbar">
        <a class="ghost-button link-button back-button icon-back-button" href="#/garden" aria-label="Back to your garden">←</a>
      </div>

      <div class="detail-shell">
        <section class="plant-hero">
          <div class="plant-hero-image">
            ${photoMarkup(plant.photo_url, `${plant.name} hero photo`, initialsFor(plant.name))}
          </div>
          <div class="plant-hero-copy">
            <p class="eyebrow">Plant detail</p>
            <div class="inline-status">
              <h2>${escapeHtml(plant.name)}</h2>
              <span class="status-pill ${escapeHtml((latest && latest.health_status) || "watch")}">${escapeHtml(statusLabel((latest && latest.health_status) || "watch"))}</span>
            </div>
            <p class="detail-meta">${escapeHtml(plant.species)} · ${escapeHtml(plant.location || "Home")}</p>
            <div class="context-block">
              <p class="support-copy">${escapeHtml(plant.notes || "No extra notes yet. Add a little context if this plant has a strong personality.")}</p>
            </div>
          </div>
        </section>

        <section class="info-row">
          <article class="info-card">
            <div class="info-card-title">
              <h3>Latest read</h3>
              <p class="status-copy">${latest ? escapeHtml(formatDate(latest.created_at)) : "No diagnosis yet"}</p>
            </div>
            ${
              latest
                ? `
                  <h3>${escapeHtml(latest.diagnosis_title)}</h3>
                  ${fallbackSummary(latest) ? `<p class="status-copy">${escapeHtml(fallbackSummary(latest))}</p>` : ""}
                `
                : `
                  <p class="status-copy">Once you upload a photo and add a note, your next step will show up here.</p>
                `
            }
          </article>
        </section>

        <section class="checkin-card">
          <div class="section-heading">
            <div>
              <p class="eyebrow">New check-in</p>
              <h2>Open a fresh diagnosis</h2>
            </div>
          </div>
          <p class="support-copy">Keep this page focused on the plant. Start the next check-in on its own screen when you are ready.</p>
          <a class="primary-button link-button inline-cta" href="#/plant/${encodeURIComponent(plant.id)}/checkin">New check-in</a>
        </section>

        <section>
          <div class="section-heading">
            <div>
              <p class="eyebrow">Plant progression</p>
              <h2>Photo history</h2>
            </div>
          </div>
          <div class="history-list">${historyMarkup}</div>
        </section>

        <section class="danger-zone">
          <button class="ghost-button danger-button" id="delete-plant" type="button">Delete plant</button>
        </section>
      </div>
    </div>
  `;

  document.getElementById("delete-plant")?.addEventListener("click", handleDeletePlant);
}

function renderCheckinView() {
  const plant = state.selectedPlant;
  if (!plant) {
    detailViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Plant not found</p>
        <h2>Let’s head back to your garden</h2>
        <a class="ghost-button link-button" href="#/garden">Back to list</a>
      </div>
    `;
    return;
  }

  const previewMarkup = state.detailPreviewUrl
    ? `<div class="preview-image"><img src="${escapeHtml(state.detailPreviewUrl)}" alt="Preview of your new plant check-in photo" /></div>`
    : placeholderPhotoMarkup("empty-checkin-photo");

  detailViewEl.innerHTML = `
    <div class="detail-stack">
      <div class="detail-topbar">
        <a class="ghost-button link-button back-button icon-back-button" href="#/plant/${encodeURIComponent(plant.id)}" aria-label="Back to plant detail">←</a>
      </div>

      <div class="detail-shell">
        <section class="checkin-card">
          <div class="section-heading">
            <div>
              <p class="eyebrow">New check-in</p>
              <h2>Diagnose ${escapeHtml(plant.name)}</h2>
            </div>
          </div>
          <p class="detail-meta">${escapeHtml(plant.species)} · ${escapeHtml(plant.location || "Home")}</p>
          <form id="checkin-form" class="checkin-form stack-form">
            <div class="intake-composer checkin-composer">
              <div id="photo-preview-slot">${previewMarkup}</div>
              <input id="checkin-photo" name="photo" type="file" accept="image/*" hidden />
              <div class="composer-body">
                <textarea
                  id="checkin-note"
                  name="note"
                  rows="4"
                  placeholder="Add a photo, then tell My Garden what changed today: drooping leaves, dry soil, yellow spots, crispy edges, or anything else you’re noticing."
                ></textarea>
              </div>
            </div>
            <button class="primary-button" type="submit">Save diagnosis</button>
          </form>
        </section>
      </div>
    </div>
  `;

  const photoInput = document.getElementById("checkin-photo");
  const checkinForm = document.getElementById("checkin-form");
  if (photoInput) {
    photoInput.addEventListener("change", handleDetailPhotoPreview);
  }
  document.getElementById("empty-checkin-photo")?.addEventListener("click", () => {
    photoInput?.click();
  });
  if (checkinForm) {
    checkinForm.addEventListener("submit", handleCheckinSubmit);
  }
}

function updateDetailPreviewSlot() {
  const slot = document.getElementById("photo-preview-slot");
  if (!slot) return;
  slot.innerHTML = state.detailPreviewUrl
    ? `<div class="preview-image"><img src="${escapeHtml(state.detailPreviewUrl)}" alt="Preview of your new plant check-in photo" /></div>`
    : placeholderPhotoMarkup("empty-checkin-photo");
  document.getElementById("empty-checkin-photo")?.addEventListener("click", () => {
    document.getElementById("checkin-photo")?.click();
  });
}

function handleIntakePhotoChange(event) {
  clearIntakePreview();
  const file = event.target.files?.[0];
  if (file) {
    state.intakePreviewUrl = URL.createObjectURL(file);
  }
  resetIntakeSuggestion();
  renderAddView();
}

function handleDetailPhotoPreview(event) {
  clearDetailPreview();
  const file = event.target.files?.[0];
  if (!file) {
    updateDetailPreviewSlot();
    return;
  }
  state.detailPreviewUrl = URL.createObjectURL(file);
  updateDetailPreviewSlot();
}

function bindDynamicRouteLinks(root) {
  root.querySelectorAll("[data-open-plant]").forEach((button) => {
    button.addEventListener("click", () => {
      const plantId = button.getAttribute("data-open-plant");
      if (!plantId) return;
      clearDetailPreview();
      setRoute(`/plant/${encodeURIComponent(plantId)}`);
    });
  });
}

async function loadPlants() {
  const response = await fetch("/api/plants");
  if (!response.ok) {
    throw new Error("Could not load plants.");
  }
  const data = await response.json();
  state.plants = data.plants || [];
}

async function loadPlantDetail(plantId) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}`);
  if (!response.ok) {
    if (response.status === 404) {
      state.selectedPlant = null;
      return;
    }
    throw new Error("Could not load plant detail.");
  }
  const data = await response.json();
  state.selectedPlant = data.plant;
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
    const response = await fetch(`/api/plants/${encodeURIComponent(route.plantId)}`, {
      method: "DELETE",
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Could not delete plant.");
    }
    clearDetailPreview();
    await loadPlants();
    state.selectedPlant = null;
    showToast("Plant deleted");
    setRoute("/garden");
  } catch (error) {
    showToast(error.message || "Could not delete plant");
  }
}

async function fetchIntakeSuggestion(signature) {
  const file = intakePhotoInput?.files?.[0];
  if (!file) {
    resetIntakeSuggestion();
    renderAddView();
    return;
  }

  const requestId = ++state.intakeSuggestionRequestId;
  state.intakeSuggestionLoading = true;
  renderAddView();

  const payload = new FormData();
  payload.append("photo", file);

  try {
    const response = await fetch("/api/plant-identity-preview", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Could not identify this plant.");
    }
    if (requestId !== state.intakeSuggestionRequestId) {
      return;
    }
    state.intakeSuggestion = normalizeSuggestion(data.suggestion || {});
    state.intakeDiagnosis = normalizeDiagnosis(data.diagnosis);
    state.intakeUploadToken = String(data.upload_token || "").trim();
    state.intakeSuggestionSignature = signature;
    syncIntakePlantNameFromSuggestion(state.intakeSuggestion);
  } catch (error) {
    if (requestId !== state.intakeSuggestionRequestId) {
      return;
    }
    state.intakeSuggestion = normalizeSuggestion({
      source: "heuristic",
      caption: error.message || "We could not analyze that photo just yet.",
    });
    state.intakeDiagnosis = null;
    state.intakeUploadToken = "";
    state.intakeSuggestionSignature = signature;
  } finally {
    if (requestId === state.intakeSuggestionRequestId) {
      state.intakeSuggestionLoading = false;
      renderAddView();
    }
  }
}

function handleIdentifyPlantClick() {
  const signature = intakeSignature();
  if (!signature) {
    showToast("Add a photo first");
    return;
  }
  void fetchIntakeSuggestion(signature);
}

function renderCurrentView() {
  setActiveTab();

  if (state.route.name === "add") {
    showView("add");
    renderAddView();
    return;
  }

  if (state.route.name === "garden") {
    showView("garden");
    renderGarden();
    return;
  }

  showView("detail");
  if (state.route.name === "checkin") {
    renderCheckinView();
    return;
  }
  renderDetail();
}

async function syncRoute() {
  const route = routeFromHash();
  state.route = route;
  await loadPlants();

  if (route.name === "detail" || route.name === "checkin") {
    const exists = state.plants.some((plant) => plant.id === route.plantId);
    if (!exists) {
      state.selectedPlant = null;
      showToast("That plant could not be found");
      setRoute("/garden");
      return;
    }
    await loadPlantDetail(route.plantId);
  } else {
    state.selectedPlant = null;
  }

  renderCurrentView();
}

async function handleAddPlantSubmit(event) {
  event.preventDefault();
  const photoFile = intakePhotoInput?.files?.[0] || null;
  const locationValue = intakeLocationInput?.value?.trim() || "";
  const customNameValue = plantNameInput?.value?.trim() || "";

  if (!photoFile) {
    showToast("Take a photo first");
    return;
  }

  const payload = new FormData();
  if (locationValue) {
    payload.append("location", locationValue);
  }
  const activeSuggestion = state.intakeSuggestion;
  const hasFreshSuggestion = state.intakeSuggestionSignature === intakeSignature();
  const activeDiagnosis = hasFreshSuggestion ? state.intakeDiagnosis : null;
  const activeUploadToken = hasFreshSuggestion ? state.intakeUploadToken : "";
  if (!hasFreshSuggestion) {
    showToast("Tap Identify plant first");
    return;
  }
  const resolvedName = customNameValue || (hasFreshSuggestion ? activeSuggestion?.name || "" : "");
  if (!resolvedName || isUnknownSuggestionName(resolvedName)) {
    setPlantNameEditing(true);
    showToast("Name this plant before saving");
    return;
  }
  if (activeUploadToken) {
    payload.append("upload_token", activeUploadToken);
  } else {
    showToast("Please identify this plant again");
    return;
  }
  payload.append("name", resolvedName);
  if (activeSuggestion?.species && state.intakeSuggestionSignature === intakeSignature()) {
    payload.append("species", activeSuggestion.species);
  }
  if (activeDiagnosis) {
    payload.append("diagnosis_payload", JSON.stringify(activeDiagnosis));
  }

  const saveButton = document.getElementById("save-plant");
  saveButton.disabled = true;
  saveButton.textContent = "Saving...";

  try {
    const response = await fetch("/api/plants", {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Could not save plant.");
    }

    addPlantForm.reset();
    clearIntakePreview();
    resetIntakeSuggestion();
    resetPurchaseDateInput();
    renderAddView();
    showToast(`Saved ${data.plant.name}`);
    setRoute(`/plant/${encodeURIComponent(data.plant.id)}`);
  } catch (error) {
    showToast(error.message || "Could not save plant");
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "Save plant";
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
  }
  if (noteValue) {
    payload.append("note", noteValue);
  }

  submitButton.disabled = true;
  submitButton.textContent = "Diagnosing...";

  try {
    const response = await fetch(`/api/plants/${encodeURIComponent(route.plantId)}/checkins`, {
      method: "POST",
      body: payload,
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.error || "Could not save check-in.");
    }

    clearDetailPreview();
    showToast("Check-in saved");
    setRoute(`/plant/${encodeURIComponent(route.plantId)}`);
  } catch (error) {
    showToast(error.message || "Could not save check-in");
  } finally {
    submitButton.disabled = false;
    submitButton.textContent = "Save diagnosis";
  }
}

function bindStaticEvents() {
  tabButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const route = button.getAttribute("data-route");
      if (!route) return;
      clearDetailPreview();
      setRoute(`/${route}`);
    });
  });

  addPlantForm.addEventListener("submit", handleAddPlantSubmit);
  intakePhotoInput?.addEventListener("change", handleIntakePhotoChange);
  plantNameInput?.addEventListener("input", () => {
    state.intakePlantName = plantNameInput.value;
    state.intakePlantNameTouched = true;
  });
  plantNameInput?.addEventListener("blur", () => {
    state.intakePlantName = plantNameInput.value.trim();
    if (state.intakePlantName) {
      setPlantNameEditing(false);
    }
  });
  plantNameInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      state.intakePlantName = plantNameInput.value.trim();
      if (state.intakePlantName) {
        setPlantNameEditing(false);
      }
    }
    if (event.key === "Escape") {
      event.preventDefault();
      plantNameInput.value = state.intakePlantName;
      setPlantNameEditing(false);
    }
  });
  editPlantNameButton?.addEventListener("click", () => {
    setPlantNameEditing(true);
  });
  identifyPlantButton?.addEventListener("click", handleIdentifyPlantClick);
  window.addEventListener("hashchange", syncRoute);
}

async function boot() {
  bindStaticEvents();
  resetPurchaseDateInput();
  void registerServiceWorker();

  if (!window.location.hash || window.location.hash === "#/overview") {
    window.location.hash = "#/add";
  }

  resetIntakeSuggestion();

  try {
    await syncRoute();
  } catch (error) {
    addViewEl.innerHTML = `
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
