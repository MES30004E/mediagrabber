export const HOST = "com.morgan.media_downloader.youtube";
const youtube = value => {
  try { const u = new URL(value); return u.protocol === "https:" && (u.hostname === "youtube.com" || u.hostname.endsWith(".youtube.com")); }
  catch { return false; }
};

export async function connectivity(api) {
  try { return (await api.runtime.sendNativeMessage(HOST, {type: "ping"})).status === "ready"; }
  catch { return false; }
}

export async function capture(api, consent) {
  if (consent !== true) throw new Error("Approve transferring YouTube session cookies first.");
  if (!await api.extension.isAllowedIncognitoAccess() || api.extension.inIncognitoContext !== true)
    throw new Error("Enable Allow in Incognito, then open this popup inside the Incognito YouTube window.");
  const [tab] = await api.tabs.query({active: true, currentWindow: true});
  if (!tab || tab.incognito !== true || !youtube(tab.url)) throw new Error("Select an HTTPS YouTube tab in Incognito.");
  const others = await api.tabs.query({url: "https://*.youtube.com/*"});
  if (others.some(t => t.incognito && t.id !== tab.id)) throw new Error("Close other Incognito YouTube tabs before capture to reduce session rotation.");
  const stores = await api.cookies.getAllCookieStores();
  const candidates = stores.filter(s => s.tabIds.includes(tab.id));
  if (candidates.length !== 1) throw new Error("Cannot uniquely identify this Incognito cookie store. No cookies were captured.");
  const storeId = candidates[0].id;
  const pending = await api.runtime.sendNativeMessage(HOST, {type: "hello"});
  if (pending.status !== "pending") throw new Error("Start Connect or Reconnect in Morgan before capture.");
  await api.tabs.update(tab.id, {url: "https://www.youtube.com/robots.txt"});
  let ready = false;
  for (let i = 0; i < 100; i++) {
    const current = await api.tabs.get(tab.id);
    if (!current.incognito || !youtube(current.url)) throw new Error("Incognito tab changed; capture stopped.");
    if (current.status === "complete" && new URL(current.url).pathname === "/robots.txt") { ready = true; break; }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!ready) throw new Error("The export preparation page did not finish loading. Retry without closing this window.");
  const raw = await api.cookies.getAll({domain: "youtube.com", storeId});
  if (!raw.length || raw.length > 200) throw new Error("No usable YouTube cookies found, or capture exceeds the safe limit. Sign in and retry.");
  const fields = ["name", "value", "domain", "path", "secure", "httpOnly", "hostOnly", "session", "expirationDate", "sameSite", "storeId"];
  const cookies = raw.map(c => {
    if (c.storeId !== storeId || !youtube(`https://${c.domain.replace(/^\./, "")}/`) || c.partitionKey)
      throw new Error("Unexpected cookie scope or partition. Nothing was imported.");
    return Object.fromEntries(fields.filter(k => c[k] !== undefined).map(k => [k, c[k]]));
  });
  const reply = await api.runtime.sendNativeMessage(HOST, {
    type: "capture", operation_id: pending.operation_id, nonce: pending.nonce,
    consent: true, incognito: true, store_id: storeId, cookies,
  });
  if (reply.status !== "imported") throw new Error("Morgan rejected the import or Keychain storage failed. Reconnect in Morgan and retry.");
  return {status: "imported", cookieCount: reply.cookie_count};
}
