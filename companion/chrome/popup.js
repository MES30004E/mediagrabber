import {capture, connectivity} from "./core.mjs";
const status = document.querySelector("#status");
const button = document.querySelector("#capture");
const consent = document.querySelector("#consent");
let allowed = false;
const update = () => { button.disabled = !allowed || !consent.checked; };
async function check() {
  allowed = await chrome.extension.isAllowedIncognitoAccess() && chrome.extension.inIncognitoContext === true;
  const connected = await connectivity(chrome);
  status.textContent = !allowed ? "Incognito access required. Enable it in Chrome Details and open this popup in Incognito."
    : connected ? "Local host ready. Start Connect in Morgan, sign in, then approve capture." : "Local host unavailable. Use Companion Setup in Morgan and retry.";
  update();
}
consent.addEventListener("change", update);
document.querySelector("#check").addEventListener("click", () => check().catch(() => { status.textContent = "Permission check failed. Reload the extension and retry."; }));
document.querySelector("#open").addEventListener("click", () => chrome.windows.create({incognito: true, url: "https://www.youtube.com/"}).catch(() => { status.textContent = "Chrome could not open Incognito. Check browser policy."; }));
button.addEventListener("click", async () => {
  button.disabled = true;
  try {
    await capture(chrome, consent.checked);
    status.textContent = "Session imported into Morgan's Keychain. Close this Incognito window now, then Verify Session in Morgan. Import is not proof of sign-in or private permissions.";
    consent.checked = false;
  } catch (error) {
    // Only our fixed, credential-free messages. Never echo native/browser errors.
    status.textContent = error instanceof Error && !String(error.message).includes("chrome")
      ? "Capture did not complete. Check Incognito permission, use one YouTube tab, start Reconnect in Morgan and retry."
      : "Capture failed. Check local host installation and reconnect in Morgan.";
  } finally { update(); }
});
check().catch(() => { status.textContent = "Setup check failed. Enable Incognito access and check Morgan's companion setup."; });
