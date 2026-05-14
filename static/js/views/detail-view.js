import {
  buildWateringCalendar,
  escapeHtml,
  fallbackSummary,
  formatDate,
  formatDateOnly,
  historyDisclosureMarkup,
  initialsFor,
  isNeutralStatus,
  photoMarkup,
  placeholderPhotoMarkup,
  statusLabel,
  todayInputValue,
} from "/static/js/helpers.js";

export function renderDetail({
  state,
  detailViewEl,
  syncDetailEditorState,
  actions,
}) {
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

  syncDetailEditorState();

  const latest = plant.latest_checkin;
  const heroStatus = (latest && latest.health_status) || "watch";
  const showHeroStatus = !isNeutralStatus(heroStatus);
  const wateringReferenceDate = new Date();
  wateringReferenceDate.setDate(1);
  wateringReferenceDate.setMonth(
    wateringReferenceDate.getMonth() + Number(state.detailWateringMonthOffset || 0),
  );
  const wateringCalendar = buildWateringCalendar(plant.watering_dates || [], wateringReferenceDate);
  const wateredDates = new Set(
    Array.isArray(plant.watering_dates)
      ? plant.watering_dates.map((value) => String(value || "").trim()).filter(Boolean)
      : [],
  );
  const wateredToday = wateredDates.has(todayInputValue());
  const lastWateredLabel = plant.last_watered_on
    ? formatDateOnly(plant.last_watered_on)
    : "";
  const historyMarkup = plant.checkins.length
    ? plant.checkins.map((checkin) => historyDisclosureMarkup(checkin, plant)).join("")
    : `
      <div class="empty-card">
        <h3>No check-ins yet</h3>
        <p class="empty-copy">Open a check-in when you want to save the first photo and diagnosis for this plant.</p>
      </div>
    `;

  detailViewEl.innerHTML = `
    <div class="detail-stack">
      <div class="detail-shell">
        <div class="detail-topbar">
          <a class="ghost-button link-button back-button icon-back-button" href="#/garden" aria-label="Back to your garden">←</a>
        </div>
        <section class="plant-hero">
          <div class="plant-hero-image">
            ${photoMarkup(plant.photo_url, `${plant.name} hero photo`, initialsFor(plant.name))}
          </div>
          <div class="plant-hero-copy">
            <p class="eyebrow">Plant detail</p>
            <div class="detail-hero-head">
              <div class="detail-name-stack">
                ${
                  state.detailNameEditing
                    ? `
                      <input
                        id="detail-name-input"
                        class="detail-name-input"
                        type="text"
                        value="${escapeHtml(state.detailDraftName)}"
                        aria-label="Edit plant name"
                        ${state.detailNameSaving ? "disabled" : ""}
                      />
                    `
                    : `
                      <h2>${escapeHtml(plant.name)}</h2>
                      <button
                        id="edit-detail-name"
                        class="icon-edit-button detail-edit-button"
                        type="button"
                        aria-label="Edit plant name"
                      >✎</button>
                    `
                }
              </div>
              ${
                showHeroStatus
                  ? `<span class="status-pill ${escapeHtml(heroStatus)}">${escapeHtml(statusLabel(heroStatus))}</span>`
                  : ""
              }
            </div>
            ${plant.chinese_name ? `<p class="detail-secondary-name">${escapeHtml(plant.chinese_name)}</p>` : ""}
            <p class="detail-meta">${escapeHtml(plant.species)} · ${escapeHtml(plant.location || "Home")}</p>
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
                  ${
                    latest.note
                      ? `
                        <div class="history-panel-block latest-note-block">
                          <p class="history-panel-label">What you noted</p>
                          <p class="history-copy">${escapeHtml(latest.note)}</p>
                        </div>
                      `
                      : ""
                  }
                `
                : `
                  <p class="status-copy">Once you upload a photo and add a note, your next step will show up here.</p>
                `
            }
            ${
              latest
                ? `
                  <a
                    class="ghost-button link-button latest-followup-button"
                    href="#/plant/${encodeURIComponent(plant.id)}/chat?checkin_id=${encodeURIComponent(latest.id)}"
                  >Ask follow-up</a>
                `
                : ""
            }
          </article>
          <article class="info-card watering-card">
            <div class="watering-head">
              <div>
                <p class="eyebrow">Watering</p>
                <h3>${
                  wateredToday
                    ? "Watered today"
                    : lastWateredLabel
                      ? `Last watered ${escapeHtml(lastWateredLabel)}`
                      : "Not watered yet"
                }</h3>
              </div>
            </div>
            <div class="watering-calendar">
              <div class="watering-calendar-head">
                <button
                  id="watering-prev-month"
                  class="watering-month-button"
                  type="button"
                  aria-label="Previous month"
                >&lsaquo;</button>
                <p class="watering-calendar-label">${escapeHtml(wateringCalendar.monthLabel)}</p>
                <button
                  id="watering-next-month"
                  class="watering-month-button"
                  type="button"
                  aria-label="Next month"
                >&rsaquo;</button>
              </div>
              <div class="watering-weekdays" aria-hidden="true">
                ${wateringCalendar.weekdays.map((label) => `<span>${escapeHtml(label)}</span>`).join("")}
              </div>
              <div class="watering-grid">
                ${wateringCalendar.cells.map((cell) => {
                  if (!cell.inMonth) {
                    return `<div class="watering-day watering-day-empty" aria-hidden="true"></div>`;
                  }
                  const classes = [
                    "watering-day",
                    cell.watered ? "is-watered" : "",
                    cell.isToday ? "is-today" : "",
                  ].filter(Boolean).join(" ");
                  return `
                    <button
                      class="${classes}"
                      type="button"
                      data-watering-date="${escapeHtml(cell.key)}"
                      title="${escapeHtml(cell.key)}"
                      aria-label="${escapeHtml(cell.key)}${cell.watered ? ", watered" : ", not watered"}${cell.isToday ? ", today" : ""}"
                      aria-pressed="${cell.watered ? "true" : "false"}"
                    >
                      <span class="watering-day-number">${escapeHtml(cell.label)}</span>
                    </button>
                  `;
                }).join("")}
              </div>
            </div>
          </article>
        </section>

        <section class="checkin-shortcut">
          <a class="primary-button link-button inline-cta" href="#/plant/${encodeURIComponent(plant.id)}/checkin">New check-in</a>
        </section>

        <section>
          <div class="section-heading">
            <div>
              <p class="eyebrow">Plant log</p>
              <h2>Check-in history</h2>
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

  document.getElementById("edit-detail-name")?.addEventListener("click", actions.onStartEditName);

  const detailNameInput = document.getElementById("detail-name-input");
  if (detailNameInput) {
    detailNameInput.addEventListener("input", () => {
      actions.onDetailNameInput(detailNameInput.value);
    });
    detailNameInput.addEventListener("blur", () => {
      void actions.onSaveDetailName();
    });
    detailNameInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        void actions.onSaveDetailName();
      }
      if (event.key === "Escape") {
        event.preventDefault();
        actions.onCancelEditName();
      }
    });
    queueMicrotask(() => {
      detailNameInput.focus();
      detailNameInput.select();
    });
  }

  document.getElementById("delete-plant")?.addEventListener("click", actions.onDeletePlant);
  document.getElementById("watering-prev-month")?.addEventListener("click", actions.onPreviousWateringMonth);
  document.getElementById("watering-next-month")?.addEventListener("click", actions.onNextWateringMonth);
  detailViewEl.querySelectorAll("[data-watering-date]").forEach((button) => {
    button.addEventListener("click", () => {
      const wateredOn = button.getAttribute("data-watering-date");
      if (wateredOn) {
        void actions.onToggleWateringDate(wateredOn);
      }
    });
  });
  detailViewEl.querySelectorAll("[data-delete-checkin]").forEach((button) => {
    button.addEventListener("click", () => {
      const checkinId = button.getAttribute("data-delete-checkin");
      if (checkinId) {
        void actions.onDeleteCheckin(checkinId);
      }
    });
  });
}

export function renderCheckinView({
  state,
  detailViewEl,
  actions,
}) {
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
      <div class="detail-shell">
        <div class="detail-topbar">
          <a class="ghost-button link-button back-button icon-back-button" href="#/plant/${encodeURIComponent(plant.id)}" aria-label="Back to plant detail">←</a>
        </div>
        <section class="checkin-card">
          <div class="section-heading">
            <div>
              <p class="eyebrow">New check-in</p>
              <h2>Diagnose ${escapeHtml(plant.name)}</h2>
            </div>
          </div>
          ${plant.chinese_name ? `<p class="detail-secondary-name">${escapeHtml(plant.chinese_name)}</p>` : ""}
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
            <button class="primary-button" type="submit">Diagnose and save</button>
          </form>
        </section>
      </div>
    </div>
  `;

  const photoInput = document.getElementById("checkin-photo");
  const checkinForm = document.getElementById("checkin-form");
  if (photoInput) {
    photoInput.addEventListener("change", actions.onDetailPhotoPreview);
  }
  document.getElementById("empty-checkin-photo")?.addEventListener("click", actions.onOpenCheckinPhotoPicker);
  if (checkinForm) {
    checkinForm.addEventListener("submit", actions.onCheckinSubmit);
  }
}

export function updateDetailPreviewSlot({
  state,
  onOpenCheckinPhotoPicker,
}) {
  const slot = document.getElementById("photo-preview-slot");
  if (!slot) return;
  slot.innerHTML = state.detailPreviewUrl
    ? `<div class="preview-image"><img src="${escapeHtml(state.detailPreviewUrl)}" alt="Preview of your new plant check-in photo" /></div>`
    : placeholderPhotoMarkup("empty-checkin-photo");
  document.getElementById("empty-checkin-photo")?.addEventListener("click", onOpenCheckinPhotoPicker);
}
