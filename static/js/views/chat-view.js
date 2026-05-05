import {
  escapeHtml,
  formatDate,
} from "/static/js/helpers.js";

function chatContextCard(checkin) {
  if (!checkin) {
    return "";
  }
  const note = String(checkin.note || "").trim();
  return `
    <section class="chat-context-card">
      <div class="chat-context-head">
        <p class="eyebrow">Active context</p>
        <p class="status-copy">${escapeHtml(formatDate(checkin.created_at))}</p>
      </div>
      <h3>${escapeHtml(checkin.diagnosis_title || "Recent diagnosis")}</h3>
      ${
        checkin.diagnosis_summary
          ? `<p class="support-copy">${escapeHtml(checkin.diagnosis_summary)}</p>`
          : ""
      }
      ${
        note
          ? `
            <div class="history-panel-block">
              <p class="history-panel-label">What you noted</p>
              <p class="history-copy">${escapeHtml(note)}</p>
            </div>
          `
          : ""
      }
    </section>
  `;
}

function messageMarkup(message) {
  const role = String(message.role || "").trim().toLowerCase() || "assistant";
  const isUser = role === "user";
  const body = String(message.body || "").trim();
  const suggestedActions = Array.isArray(message.suggested_actions) ? message.suggested_actions : [];
  const watchSignals = Array.isArray(message.watch_signals) ? message.watch_signals : [];

  return `
    <article class="chat-bubble ${isUser ? "chat-bubble-user" : "chat-bubble-assistant"}">
      <div class="chat-bubble-head">
        <p class="eyebrow">${isUser ? "You" : "My Garden"}</p>
        <p class="status-copy">${escapeHtml(formatDate(message.created_at))}</p>
      </div>
      <div class="chat-bubble-copy">
        <p>${escapeHtml(body)}</p>
      </div>
      ${
        !isUser && (suggestedActions.length || watchSignals.length)
          ? `
            <div class="chat-bubble-meta">
              ${
                suggestedActions.length
                  ? `
                    <div class="history-panel-block">
                      <p class="history-panel-label">Next steps</p>
                      <ul class="care-list compact-care-list">
                        ${suggestedActions.map((step) => `<li>${escapeHtml(step)}</li>`).join("")}
                      </ul>
                    </div>
                  `
                  : ""
              }
              ${
                watchSignals.length
                  ? `
                    <div class="history-panel-block">
                      <p class="history-panel-label">Watch for</p>
                      <ul class="care-list compact-care-list">
                        ${watchSignals.map((signal) => `<li>${escapeHtml(signal)}</li>`).join("")}
                      </ul>
                    </div>
                  `
                  : ""
              }
            </div>
          `
          : ""
      }
    </article>
  `;
}

export function renderChatView({
  state,
  chatViewEl,
  actions,
}) {
  const plant = state.selectedPlant;
  if (!plant) {
    chatViewEl.innerHTML = `
      <div class="panel empty-card">
        <p class="eyebrow">Plant not found</p>
        <h2>Let’s head back to your garden</h2>
        <a class="ghost-button link-button" href="#/garden">Back to list</a>
      </div>
    `;
    return;
  }

  const messages = Array.isArray(state.chatMessages) ? state.chatMessages : [];
  const focusedCheckin = state.chatFocusedCheckin || plant.latest_checkin || null;
  const suggestedPrompts = Array.isArray(state.chatSuggestedPrompts) ? state.chatSuggestedPrompts : [];

  chatViewEl.innerHTML = `
    <div class="detail-stack">
      <div class="detail-shell chat-shell">
        <div class="detail-topbar">
          <a class="ghost-button link-button back-button icon-back-button" href="#/plant/${encodeURIComponent(plant.id)}" aria-label="Back to plant detail">←</a>
        </div>
        <section class="chat-header-block">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Plant chat</p>
              <h2>Ask about ${escapeHtml(plant.name)}</h2>
            </div>
          </div>
          ${plant.chinese_name ? `<p class="detail-secondary-name">${escapeHtml(plant.chinese_name)}</p>` : ""}
          <p class="detail-meta">${escapeHtml(plant.species)} · ${escapeHtml(plant.location || "Home")}</p>
        </section>

        ${chatContextCard(focusedCheckin)}

        <section class="chat-thread">
          ${
            messages.length
              ? `<div class="chat-message-list">${messages.map((message) => messageMarkup(message)).join("")}</div>`
              : `
                <div class="empty-card">
                  <h3>Start the follow-up here</h3>
                  <p class="empty-copy">Ask a plant-specific question and My Garden will answer with the saved diagnosis and recent history in mind.</p>
                </div>
              `
          }
        </section>

        ${
          suggestedPrompts.length
            ? `
              <section class="chat-prompts">
                <p class="history-panel-label">Try asking</p>
                <div class="chat-prompt-list">
                  ${suggestedPrompts.map((prompt) => `
                    <button
                      class="ghost-button chat-prompt-button"
                      type="button"
                      data-chat-prompt="${escapeHtml(prompt)}"
                    >${escapeHtml(prompt)}</button>
                  `).join("")}
                </div>
              </section>
            `
            : ""
        }

        <section class="chat-composer-card">
          <form id="plant-chat-form" class="checkin-form stack-form">
            <textarea
              id="plant-chat-input"
              name="body"
              rows="3"
              placeholder="Ask a follow-up question about this plant..."
              ${state.chatSending ? "disabled" : ""}
            >${escapeHtml(state.chatDraft || "")}</textarea>
            <button class="primary-button" type="submit" ${state.chatSending ? "disabled" : ""}>
              ${state.chatSending ? "Thinking..." : "Send"}
            </button>
          </form>
        </section>
      </div>
    </div>
  `;

  chatViewEl.querySelectorAll("[data-chat-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      const prompt = button.getAttribute("data-chat-prompt");
      if (prompt) {
        void actions.onSendChatPrompt(prompt);
      }
    });
  });

  document.getElementById("plant-chat-input")?.addEventListener("input", (event) => {
    actions.onChatDraftInput(event.currentTarget.value);
  });
  document.getElementById("plant-chat-form")?.addEventListener("submit", actions.onChatSubmit);
}
