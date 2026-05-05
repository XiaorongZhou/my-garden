export function routeFromHash(hash = window.location.hash) {
  const raw = String(hash).replace(/^#\/?/, "").trim();
  const [path, queryString = ""] = raw.split("?");
  const query = new URLSearchParams(queryString);

  if (!path || path === "overview" || path === "add") {
    return { name: "add" };
  }
  if (path === "garden") {
    return { name: "garden" };
  }
  const checkinMatch = path.match(/^plant\/(.+)\/checkin$/);
  if (checkinMatch) {
    return { name: "checkin", plantId: decodeURIComponent(checkinMatch[1]) };
  }
  const chatMatch = path.match(/^plant\/(.+)\/chat$/);
  if (chatMatch) {
    const checkinId = String(query.get("checkin_id") || "").trim();
    return {
      name: "chat",
      plantId: decodeURIComponent(chatMatch[1]),
      checkinId: checkinId || null,
    };
  }
  if (path.startsWith("plant/")) {
    const plantId = decodeURIComponent(path.slice("plant/".length));
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
