async function parseJson(response, fallbackMessage) {
  let data = {};
  try {
    data = await response.json();
  } catch (_error) {
    data = {};
  }
  if (!response.ok) {
    throw new Error(data.error || fallbackMessage);
  }
  return data;
}

let currentSessionToken = "";

function authHeaders(extraHeaders = {}) {
  if (!currentSessionToken) {
    return extraHeaders;
  }
  return {
    ...extraHeaders,
    Authorization: `Bearer ${currentSessionToken}`,
  };
}

export function setApiSessionToken(sessionToken) {
  currentSessionToken = String(sessionToken || "").trim();
}

export async function fetchSession() {
  const response = await fetch("/api/session", {
    headers: authHeaders(),
  });
  return parseJson(response, "Could not load your garden profile.");
}

export async function createSessionRequest(payload) {
  const response = await fetch("/api/session", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  return parseJson(response, "Could not open your garden.");
}

export async function fetchPlants() {
  const response = await fetch("/api/plants", {
    headers: authHeaders(),
  });
  const data = await parseJson(response, "Could not load plants.");
  return data.plants || [];
}

export async function fetchPlantDetail(plantId) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}`, {
    headers: authHeaders(),
  });
  if (response.status === 404) {
    return null;
  }
  const data = await parseJson(response, "Could not load plant detail.");
  return data.plant;
}

export async function fetchPlantChat(plantId, checkinId = "") {
  const suffix = checkinId ? `?checkin_id=${encodeURIComponent(checkinId)}` : "";
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}/chat${suffix}`, {
    headers: authHeaders(),
  });
  const data = await parseJson(response, "Could not load plant chat.");
  return {
    plant: data.plant,
    thread: data.thread,
    messages: data.messages || [],
    focused_checkin: data.focused_checkin || null,
    suggested_prompts: data.suggested_prompts || [],
  };
}

export async function patchPlant(plantId, patch) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}`, {
    method: "PATCH",
    headers: authHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(patch),
  });
  const data = await parseJson(response, "Could not update plant.");
  return data.plant;
}

export async function deletePlantRequest(plantId) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return parseJson(response, "Could not delete plant.");
}

export async function requestPlantIdentityPreview(payload) {
  const response = await fetch("/api/plant-identity-preview", {
    method: "POST",
    headers: authHeaders(),
    body: payload,
  });
  return parseJson(response, "Could not identify this plant.");
}

export async function createPlantRequest(payload) {
  const response = await fetch("/api/plants", {
    method: "POST",
    headers: authHeaders(),
    body: payload,
  });
  return parseJson(response, "Could not save plant.");
}

export async function createCheckinRequest(plantId, payload) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}/checkins`, {
    method: "POST",
    headers: authHeaders(),
    body: payload,
  });
  return parseJson(response, "Could not save check-in.");
}

export async function createWateringRequest(plantId, payload = {}) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}/waterings`, {
    method: "POST",
    headers: authHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  });
  return parseJson(response, "Could not save watering.");
}

export async function createPlantChatMessageRequest(plantId, payload) {
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}/chat/messages`, {
    method: "POST",
    headers: authHeaders({
      "Content-Type": "application/json",
    }),
    body: JSON.stringify(payload),
  });
  return parseJson(response, "Could not send follow-up.");
}

export async function deleteCheckinRequest(checkinId) {
  const response = await fetch(`/api/checkins/${encodeURIComponent(checkinId)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return parseJson(response, "Could not delete diagnosis.");
}

export async function deleteWateringRequest(plantId, wateredOn = "") {
  const suffix = wateredOn ? `?date=${encodeURIComponent(wateredOn)}` : "";
  const response = await fetch(`/api/plants/${encodeURIComponent(plantId)}/waterings${suffix}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  return parseJson(response, "Could not remove watering.");
}
