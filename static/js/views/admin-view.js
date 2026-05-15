import { escapeHtml, formatDate, formatDateOnly } from "/static/js/helpers.js";

function numberText(value) {
  return new Intl.NumberFormat().format(Number(value || 0));
}

function totalActivity(day) {
  return Number(day.plants || 0)
    + Number(day.checkins || 0)
    + Number(day.waterings || 0)
    + Number(day.followups || 0);
}

function statCard(label, value, note = "") {
  return `
    <article class="admin-stat-card">
      <p class="eyebrow">${escapeHtml(label)}</p>
      <h3>${escapeHtml(numberText(value))}</h3>
      ${note ? `<p class="section-note">${escapeHtml(note)}</p>` : ""}
    </article>
  `;
}

function dailyRow(day, maxActivity) {
  const activity = totalActivity(day);
  const width = maxActivity > 0 ? Math.max(8, Math.round((activity / maxActivity) * 100)) : 0;
  return `
    <div class="admin-day-row">
      <p>${escapeHtml(formatDateOnly(day.date))}</p>
      <div class="admin-day-bar" aria-hidden="true">
        <span style="width: ${width}%"></span>
      </div>
      <p class="admin-day-count">${escapeHtml(numberText(activity))}</p>
      <p class="admin-day-detail">
        ${escapeHtml(numberText(day.plants))} plants ·
        ${escapeHtml(numberText(day.checkins))} check-ins ·
        ${escapeHtml(numberText(day.waterings))} waterings ·
        ${escapeHtml(numberText(day.followups))} chats
      </p>
    </div>
  `;
}

function gardenRow(garden) {
  return `
    <article class="admin-garden-row">
      <div>
        <h3>${escapeHtml(garden.name || "Unnamed garden")}</h3>
        <p class="section-note">${escapeHtml(garden.email || "No email")}</p>
        <p class="admin-activity-note">Last active ${escapeHtml(formatDate(garden.last_active_at))}</p>
      </div>
      <div class="admin-garden-counts">
        <span>${escapeHtml(numberText(garden.plant_count))} plants</span>
        <span>${escapeHtml(numberText(garden.checkin_count))} check-ins</span>
        <span>${escapeHtml(numberText(garden.watering_count))} waterings</span>
        <span>${escapeHtml(numberText(garden.followup_count))} chats</span>
      </div>
    </article>
  `;
}

export function renderAdminDashboard({ state, adminViewEl, onRefreshAdmin, onBackToGarden }) {
  const metrics = state.adminMetrics;
  if (state.adminLoading && !metrics) {
    adminViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Admin</p>
        <h2>Loading garden stats...</h2>
      </div>
    `;
    return;
  }

  if (!metrics) {
    adminViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Admin</p>
        <h2>Stats unavailable</h2>
        <p class="empty-copy">Sign in with the owner garden to see aggregate usage.</p>
        <button id="admin-back" class="ghost-button" type="button">Back to garden</button>
      </div>
    `;
    document.getElementById("admin-back")?.addEventListener("click", onBackToGarden);
    return;
  }

  const totals = metrics.totals || {};
  const recent = metrics.last_7_days || {};
  const daily = Array.isArray(metrics.daily) ? metrics.daily : [];
  const maxActivity = Math.max(0, ...daily.map(totalActivity));
  const gardens = Array.isArray(metrics.gardens) ? metrics.gardens : [];

  adminViewEl.innerHTML = `
    <div class="panel admin-panel">
      <div class="section-heading admin-heading">
        <div>
          <p class="eyebrow">Admin</p>
          <h2>Garden stats</h2>
          <p class="section-note">Updated ${escapeHtml(formatDate(metrics.generated_at))}</p>
        </div>
        <button id="admin-refresh" class="ghost-button" type="button" ${state.adminLoading ? "disabled" : ""}>
          ${state.adminLoading ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <section class="admin-stat-grid" aria-label="Usage totals">
        ${statCard("Gardens", totals.gardens, `${numberText(recent.active_gardens)} active this week`)}
        ${statCard("Plants", totals.plants, `${numberText(recent.plants)} added this week`)}
        ${statCard("Check-ins", totals.checkins, `${numberText(recent.checkins)} this week`)}
        ${statCard("Waterings", totals.waterings, `${numberText(recent.waterings)} this week`)}
        ${statCard("Follow-ups", totals.followups, `${numberText(recent.followups)} this week`)}
        ${statCard("AI calls", totals.ai_calls, "tracked from quota usage")}
      </section>

      <section class="admin-section">
        <div class="admin-section-head">
          <p class="eyebrow">Last 14 days</p>
          <p class="section-note">Plants, check-ins, waterings, and chats</p>
        </div>
        <div class="admin-day-list">
          ${daily.map((day) => dailyRow(day, maxActivity)).join("")}
        </div>
      </section>

      <section class="admin-section">
        <div class="admin-section-head">
          <p class="eyebrow">Gardens</p>
          <p class="section-note">${escapeHtml(numberText(gardens.length))} shown</p>
        </div>
        <div class="admin-garden-list">
          ${gardens.length ? gardens.map(gardenRow).join("") : "<p class=\"empty-copy\">No gardens yet.</p>"}
        </div>
      </section>
    </div>
  `;

  document.getElementById("admin-refresh")?.addEventListener("click", onRefreshAdmin);
}
