export function defaultSuggestion() {
  return {
    name: "Unknown Houseplant",
    species: "Unknown houseplant",
    chinese_name: "",
    confidence: "low",
    source: "idle",
    caption: "Add a photo, then tap Identify plant.",
  };
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function initialsFor(name) {
  return String(name || "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() || "")
    .join("");
}

export function formatDate(value) {
  if (!value) return "";
  const date = new Date(value);
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

export function parseDateOnly(value) {
  if (!value) return null;
  const match = String(value).trim().match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const year = Number(match[1]);
  const monthIndex = Number(match[2]) - 1;
  const day = Number(match[3]);
  return new Date(year, monthIndex, day);
}

export function formatDateOnly(value) {
  const date = parseDateOnly(value);
  if (!date) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

export function todayInputValue() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function buildWateringCalendar(wateringDates, referenceDate = new Date()) {
  const wateredSet = new Set(
    Array.isArray(wateringDates)
      ? wateringDates.map((value) => String(value || "").trim()).filter(Boolean)
      : []
  );
  const monthStart = new Date(referenceDate.getFullYear(), referenceDate.getMonth(), 1);
  const monthEnd = new Date(referenceDate.getFullYear(), referenceDate.getMonth() + 1, 0);
  const leadingBlankCount = monthStart.getDay();
  const totalCells = Math.ceil((leadingBlankCount + monthEnd.getDate()) / 7) * 7;
  const todayKey = todayInputValue();
  const monthLabel = new Intl.DateTimeFormat(undefined, {
    month: "long",
    year: "numeric",
  }).format(monthStart);

  const weekdays = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const cells = Array.from({ length: totalCells }, (_unused, index) => {
    const dayNumber = index - leadingBlankCount + 1;
    if (dayNumber < 1 || dayNumber > monthEnd.getDate()) {
      return {
        key: `blank-${index}`,
        label: "",
        inMonth: false,
        watered: false,
        isToday: false,
      };
    }

    const key = [
      monthStart.getFullYear(),
      String(monthStart.getMonth() + 1).padStart(2, "0"),
      String(dayNumber).padStart(2, "0"),
    ].join("-");

    return {
      key,
      label: String(dayNumber),
      inMonth: true,
      watered: wateredSet.has(key),
      isToday: key === todayKey,
    };
  });

  return {
    monthLabel,
    weekdays,
    cells,
  };
}

export function statusLabel(status) {
  if (status === "thriving") return "Thriving";
  if (status === "needs_care") return "Needs care";
  return "Watch";
}

export function isNeutralStatus(status) {
  return !status || status === "watch";
}

export function fallbackSummary(checkin) {
  if (!checkin) return "";
  const summary = String(checkin.diagnosis_summary || "").trim();
  if (summary) return summary;
  if (!String(checkin.note || "").trim()) {
    return "No symptom note yet. Add one quick observation next time so the read can be specific.";
  }
  return "";
}

export function photoMarkup(url, alt, fallback) {
  if (url) {
    return `<img src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" loading="lazy" decoding="async" />`;
  }
  return `<div class="empty-photo">${escapeHtml(fallback)}</div>`;
}

export function thumbnailUrlFor(photoUrl) {
  const url = String(photoUrl || "").trim();
  if (!url.startsWith("/uploads/")) {
    return url || "";
  }
  const filename = url.split("/").pop() || "";
  if (!filename || filename.startsWith("thumb-")) {
    return url;
  }
  const stem = filename.replace(/\.[^.]+$/, "");
  return `/uploads/thumb-${encodeURIComponent(stem)}.jpg`;
}

export async function createPhotoThumbnail(file, { maxSize = 360, quality = 0.72 } = {}) {
  if (!file || !String(file.type || "").startsWith("image/")) {
    return null;
  }

  const objectUrl = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.decoding = "async";
    const loaded = new Promise((resolve, reject) => {
      image.onload = resolve;
      image.onerror = reject;
    });
    image.src = objectUrl;
    await loaded;

    const sourceWidth = image.naturalWidth || image.width;
    const sourceHeight = image.naturalHeight || image.height;
    const longestSide = Math.max(sourceWidth, sourceHeight);
    if (!sourceWidth || !sourceHeight || !longestSide) {
      return null;
    }

    const scale = Math.min(1, maxSize / longestSide);
    const width = Math.max(1, Math.round(sourceWidth * scale));
    const height = Math.max(1, Math.round(sourceHeight * scale));
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) {
      return null;
    }
    context.drawImage(image, 0, 0, width, height);

    const blob = await new Promise((resolve) => {
      canvas.toBlob(resolve, "image/jpeg", quality);
    });
    if (!blob) {
      return null;
    }
    return new File([blob], "thumbnail.jpg", {
      type: "image/jpeg",
      lastModified: Date.now(),
    });
  } catch (_error) {
    return null;
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

export function historyDisclosureMarkup(checkin, plant) {
  const diagnosis = fallbackSummary(checkin);
  const ownerNote = String(checkin.note || "").trim();
  const status = checkin.health_status || "watch";
  const showStatus = !isNeutralStatus(status);
  return `
    <details class="history-card history-disclosure">
      <summary class="history-summary">
        <div class="history-photo">
          ${photoMarkup(checkin.thumbnail_url || thumbnailUrlFor(checkin.photo_url), `${plant.name} check-in`, initialsFor(plant.name))}
        </div>
        <div class="history-summary-main">
          <div class="history-title">
            <h3>${escapeHtml(checkin.diagnosis_title)}</h3>
            ${showStatus ? `<span class="status-pill ${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>` : ""}
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
        <div class="history-panel-actions">
          <a
            class="ghost-button link-button history-chat-button"
            href="#/plant/${encodeURIComponent(plant.id)}/chat?checkin_id=${encodeURIComponent(checkin.id)}"
          >Ask follow-up</a>
          <button
            class="ghost-button danger-button history-delete-button"
            type="button"
            data-delete-checkin="${escapeHtml(checkin.id)}"
          >Delete diagnosis</button>
        </div>
      </div>
    </details>
  `;
}

export function placeholderPhotoMarkup(buttonId, options = {}) {
  const label = String(options.label ?? "Photo preview").trim();
  const buttonLabel = String(options.buttonLabel || "").trim();
  return `
    <div class="intake-placeholder intake-placeholder-action">
      ${label ? `<p class="eyebrow">${escapeHtml(label)}</p>` : ""}
      <button id="${escapeHtml(buttonId)}" class="ghost-button intake-placeholder-button icon-photo-button" type="button" aria-label="Add photo">
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <path d="M8 6.5 9.4 4h5.2L16 6.5h2.2A2.8 2.8 0 0 1 21 9.3v7.4a2.8 2.8 0 0 1-2.8 2.8H5.8A2.8 2.8 0 0 1 3 16.7V9.3a2.8 2.8 0 0 1 2.8-2.8Zm4 3.1a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0 1.8a2.2 2.2 0 1 1 0 4.4 2.2 2.2 0 0 1 0-4.4Z"></path>
        </svg>
        ${buttonLabel ? `<span>${escapeHtml(buttonLabel)}</span>` : ""}
      </button>
    </div>
  `;
}

export function isUnknownSuggestionName(value) {
  return String(value || "").trim().toLowerCase() === "unknown houseplant";
}

export function hasUsefulSpeciesLabel(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return Boolean(normalized) && ![
    "unknown houseplant",
    "photo attached",
    "identifying your plant",
  ].includes(normalized);
}

export function hasUsefulChineseLabel(value) {
  return Boolean(String(value || "").trim());
}

export function suggestionMetaLabel(suggestion, isLoading) {
  if (isLoading) {
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

export function normalizeSuggestion(payload) {
  const base = defaultSuggestion();
  return {
    ...base,
    ...payload,
    name: payload?.name || base.name,
    species: payload?.species || base.species,
    chinese_name: payload?.chinese_name || base.chinese_name,
    caption: payload?.caption || base.caption,
    confidence: payload?.confidence || base.confidence,
    source: payload?.source || base.source,
  };
}

export function normalizeTip(payload) {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const body = String(payload.body || "").trim();
  if (!body) {
    return null;
  }
  return {
    title: String(payload.title || "").trim() || "Care tip",
    body,
    source: String(payload.source || "").trim() || "reference",
  };
}

export function normalizeDiagnosis(payload) {
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
