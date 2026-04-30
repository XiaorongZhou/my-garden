export function routeFromHash(hash = window.location.hash) {
  const raw = String(hash).replace(/^#\/?/, "").trim();
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

export function setRoute(nextHash, onSameHash) {
  const normalized = nextHash.startsWith("#") ? nextHash : `#${nextHash}`;
  if (window.location.hash === normalized) {
    onSameHash?.();
    return;
  }
  window.location.hash = normalized;
}
