import { defaultSuggestion, isUnknownSuggestionName } from "/static/js/helpers.js";

export function createInitialState() {
  return {
    currentUser: null,
    isAdmin: false,
    rememberedUser: null,
    language: "en",
    sessionClaimable: false,
    authSubmitting: false,
    authNeedsName: false,
    plants: [],
    adminMetrics: null,
    adminLoading: false,
    selectedPlant: null,
    route: { name: "add" },
    intakePreviewUrl: null,
    detailPreviewUrl: null,
    intakeSuggestion: defaultSuggestion(),
    intakeDiagnosis: null,
    intakeTip: null,
    intakeUploadToken: "",
    intakeSuggestionLoading: false,
    intakeSuggestionRequestId: 0,
    intakeSuggestionSignature: "",
    intakePlantName: "",
    intakePlantNameTouched: false,
    intakePlantNameEditing: false,
    detailEditorPlantId: "",
    detailDraftName: "",
    detailNameEditing: false,
    detailNameSaving: false,
    detailWateringMonthOffset: 0,
    chatThread: null,
    chatMessages: [],
    chatFocusedCheckin: null,
    chatSuggestedPrompts: [],
    chatDraft: "",
    chatSending: false,
    toastTimer: null,
  };
}

export function resetIntakeSuggestion(state) {
  state.intakeSuggestion = defaultSuggestion();
  state.intakeDiagnosis = null;
  state.intakeTip = null;
  state.intakeUploadToken = "";
  state.intakeSuggestionLoading = false;
  state.intakeSuggestionSignature = "";
  state.intakePlantName = "";
  state.intakePlantNameTouched = false;
  state.intakePlantNameEditing = false;
}

export function syncIntakePlantNameFromSuggestion(state, suggestion) {
  if (state.intakePlantNameTouched) {
    return;
  }
  state.intakePlantName = isUnknownSuggestionName(suggestion?.name) ? "" : String(suggestion?.name || "").trim();
}

export function resetDetailEditorState(state) {
  const plant = state.selectedPlant;
  state.detailEditorPlantId = plant?.id || "";
  state.detailDraftName = String(plant?.name || "");
  state.detailNameEditing = false;
  state.detailNameSaving = false;
}

export function resetChatState(state) {
  state.chatThread = null;
  state.chatMessages = [];
  state.chatFocusedCheckin = null;
  state.chatSuggestedPrompts = [];
  state.chatDraft = "";
  state.chatSending = false;
}

export function resetSessionState(state) {
  state.currentUser = null;
  state.isAdmin = false;
  state.adminMetrics = null;
  state.adminLoading = false;
  state.authNeedsName = false;
  state.authSubmitting = false;
  resetChatState(state);
}

export function syncDetailEditorState(state) {
  if (!state.selectedPlant) {
    resetDetailEditorState(state);
    return;
  }
  if (state.detailEditorPlantId !== state.selectedPlant.id) {
    resetDetailEditorState(state);
  }
}
