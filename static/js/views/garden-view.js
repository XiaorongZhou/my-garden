import { escapeHtml, initialsFor, isNeutralStatus, photoMarkup, statusLabel } from "/static/js/helpers.js";

export function renderGarden({ state, gardenViewEl, onOpenPlant, t }) {
  const copy = t?.garden || {};
  const homeLabel = copy.home || "Home";
  if (!state.plants.length) {
    gardenViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">${escapeHtml(copy.emptyEyebrow || "No plants yet")}</p>
        <h2>${escapeHtml(copy.emptyTitle || "Start with the camera")}</h2>
        <p class="empty-copy">${escapeHtml(copy.emptyCopy || "Use the Add Plant tab to snap a photo, save the plant, and create its first diagnosis.")}</p>
      </div>
    `;
    return;
  }

  const rows = state.plants
    .map((plant) => {
      const status = plant.latest_status || "watch";
      const showStatus = !isNeutralStatus(status);
      const identityMeta = plant.chinese_name
        ? `${plant.chinese_name} · ${plant.location || homeLabel}`
        : `${plant.species} · ${plant.location || homeLabel}`;
      return `
        <button class="garden-row" type="button" data-open-plant="${escapeHtml(plant.id)}">
          <div class="garden-row-thumb">
            ${photoMarkup(plant.thumbnail_url || plant.photo_url, `${plant.name} thumbnail`, initialsFor(plant.name))}
          </div>
          <div class="garden-row-main">
            <div class="garden-row-head">
              <h3>${escapeHtml(plant.name)}</h3>
              ${showStatus ? `<span class="status-pill ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>` : ""}
            </div>
            <p class="garden-row-meta">${escapeHtml(identityMeta)}</p>
            <p class="garden-row-summary">${escapeHtml(plant.latest_summary || plant.latest_title || copy.fallbackSummary || "No diagnosis yet. Start with a photo check-in.")}</p>
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
          <p class="eyebrow">${escapeHtml(copy.eyebrow || "Your garden")}</p>
          <h2>${escapeHtml(copy.title || "Plant list")}</h2>
        </div>
        <p class="section-note">${escapeHtml(copy.plantCount ? copy.plantCount(state.plants.length) : `${state.plants.length} plants`)}</p>
      </div>
      <div class="garden-list">${rows}</div>
    </div>
  `;

  gardenViewEl.querySelectorAll("[data-open-plant]").forEach((button) => {
    button.addEventListener("click", () => {
      const plantId = button.getAttribute("data-open-plant");
      if (plantId) {
        onOpenPlant(plantId);
      }
    });
  });
}
