import {
  escapeHtml,
  hasUsefulChineseLabel,
  hasUsefulSpeciesLabel,
  isUnknownSuggestionName,
  placeholderPhotoMarkup,
  statusLabel,
  suggestionMetaLabel,
} from "/static/js/helpers.js";

export function renderAddView({
  state,
  elements,
  intakeSignature,
  knownRooms,
  setPlantNameEditing,
  syncIntakePlantNameFromSuggestion,
  onOpenPhotoPicker,
}) {
  const {
    intakePhotoInput,
    roomOptionsEl,
    intakePreviewEl,
    suggestionCardEl,
    suggestedNameEl,
    suggestedChineseNameEl,
    suggestedSpeciesEl,
    suggestedMetaEl,
    suggestedCaptionEl,
    suggestedDiagnosisEl,
    suggestedDiagnosisStatusEl,
    suggestedDiagnosisTitleEl,
    suggestedDiagnosisSummaryEl,
    suggestedTipEl,
    suggestedTipTitleEl,
    suggestedTipBodyEl,
    plantNameInput,
    identifyPlantButton,
  } = elements;

  const file = intakePhotoInput?.files?.[0] || null;
  const currentSignature = intakeSignature();
  const suggestion = state.intakeSuggestionLoading
    ? {
        name: "Looking closely...",
        chinese_name: "",
        species: "Identifying your plant",
        caption: "We’re identifying the plant and drafting a first read before you save.",
        confidence: "",
        source: "loading",
      }
    : file && state.intakeSuggestionSignature !== currentSignature
      ? {
          name: "Ready when you are",
          chinese_name: "",
          species: "Photo attached",
          caption: "Tap Identify plant to preview the plant name and first read before saving.",
          confidence: "",
          source: "ready",
        }
      : state.intakeSuggestion;
  const diagnosis = state.intakeSuggestionLoading || state.intakeSuggestionSignature !== currentSignature
    ? null
    : state.intakeDiagnosis;
  const tip = state.intakeSuggestionLoading || state.intakeSuggestionSignature !== currentSignature
    ? null
    : state.intakeTip;

  const displayName = state.intakePlantNameTouched && state.intakePlantName.trim()
    ? state.intakePlantName.trim()
    : suggestion.name;

  suggestedNameEl.textContent = displayName;
  suggestedChineseNameEl.hidden = !hasUsefulChineseLabel(suggestion.chinese_name);
  suggestedChineseNameEl.textContent = hasUsefulChineseLabel(suggestion.chinese_name) ? suggestion.chinese_name : "";
  suggestedSpeciesEl.hidden = !hasUsefulSpeciesLabel(suggestion.species);
  suggestedSpeciesEl.textContent = hasUsefulSpeciesLabel(suggestion.species) ? suggestion.species : "";
  suggestedMetaEl.textContent = suggestionMetaLabel(suggestion, state.intakeSuggestionLoading);
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
  if (suggestedTipEl) {
    suggestedTipEl.hidden = !tip;
  }
  if (suggestedTipTitleEl) {
    suggestedTipTitleEl.textContent = tip?.title || "Care tip";
  }
  if (suggestedTipBodyEl) {
    suggestedTipBodyEl.textContent = tip?.body || "";
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

  document.getElementById("empty-add-photo")?.addEventListener("click", onOpenPhotoPicker);
}
