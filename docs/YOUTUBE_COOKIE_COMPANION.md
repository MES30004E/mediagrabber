# YouTube Cookie Companion

Morgan's Python/PySide6 app can receive a deliberately captured **Chrome
Incognito** YouTube session. This is separate from ordinary browser-profile
cookies. It does not decrypt Spotify, bypass Google verification, prove private
content permission, or by itself qualify a standalone distributed app.

For the packaged-host implementation and its hosted qualification scope, see
[Packaged Companion](PACKAGED_COMPANION.md). A packaged app uses its embedded
console helper and extension files; it does not register a source-Python bootstrap
or create a Desktop launcher. Chrome extension installation/Incognito approval
remain explicit user actions in both modes.

## Install and connect

From the project root, with the external drive connected and `.venv` repaired:

```sh
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.youtube_companion.setup install
```

This installs only these user-level artifacts (no administrator or Apple build
tools):

- `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/com.morgan.media_downloader.youtube.json`
- `~/Library/Application Support/Morgan Media Downloader/companion-host/host`
- `~/Library/Application Support/Morgan Media Downloader/companion-host/bootstrap.py`

No Desktop launcher is created by default. The legacy source-dependent launcher
is available only with an explicit `--development-launcher` request; it is not
the standalone application and is never created by frozen-app setup.

Existing targets are inspected; foreign/modified layouts are refused rather
than overwritten. Other native hosts/extensions are untouched. Reinstall after
moving the project or replacing the venv: these development artifacts contain
absolute paths to this checkout and Python, not bundled dependencies.

1. In Chrome, open `chrome://extensions`, enable **Developer mode**, choose
   **Load unpacked**, and select this repository's `companion/chrome` directory.
2. Confirm extension ID **cplbbpknliffempndiphmhaolpgipdgn**. The committed public
   manifest key gives a stable identity; it is not a private signing key.
3. Open extension **Details → Allow in Incognito**. Pin the extension. These
   Chrome approvals are manual; Morgan never changes browser policy.
4. Open an existing development launcher, or run the source application:

   ```sh
   PYTHONPATH=src .venv/bin/python -m morgan_media_downloader
   ```

5. In **Settings → Accounts**, click **Connect YouTube with Chrome Incognito**
   (or Reconnect). This registers the host if needed and authorizes one capture
   for five minutes. Chrome opens Incognito; use one YouTube tab and sign in.
6. From that Incognito window, open Morgan's extension. Check the consent box
   and click **Capture YouTube Session**. It prepares the tab at YouTube's
   `robots.txt`, selects the cookie store containing that exact Incognito tab,
   and sends only YouTube cookies through Native Messaging.
7. After successful import, **close Incognito promptly** to reduce YouTube cookie
   rotation. Successful Keychain storage automatically saves and activates only
   the managed authentication choice for future analysis/downloads. Return to
   Accounts and click **Verify Session**. Cancel still discards unrelated pending
   settings edits; other authentication methods still require Apply.
8. Analyse an authorized URL or `:ytwatchlater`. The documented playlist/feed
   Watch Later URLs also work. Authentication does not confer permission to a
   private item the account cannot access.

Verification distinguishes imported, readable, server-confirmed and unconfirmed
states. A boolean signed-in response is not a reliable account/channel identity:
the UI says **Signed in — account identity not confirmed** rather than guessing
from uploader metadata. No private library enumeration is used for verification.

Use **Advanced authentication** for ordinary Browser Cookies or manually supplied
Netscape cookies.txt. Neither is presented as an Incognito capture fallback.
The extension's **Check local connection** reports host reachability and Chrome's
Incognito flags to the current capture operation, without reading cookies. It is
not a login test or proof that a transfer occurred. Accounts distinguishes host
registration from Chrome-reported readiness, authorization, transfer, storage and
verification. **Check downloader/provider** is a separate prerequisite check:
HTTP ping or script discovery is not proof of token generation or a working
download. Provider details/paths and unsanitized errors are not shown there.
Reconnect creates a new pending authorization; no transfer is replayed automatically.

Verification time is UTC and scoped to the current Settings window, not a stored
account identity or cross-restart guarantee. Source, network, provider and runtime
changes invalidate evidence; late background results cannot verify a changed
configuration. Accepted captures awaiting Keychain completion are reconciled
before unused authorization expiry. A busy native host does not freeze the GUI
or cause an accepted import receipt to be discarded.

## Storage and security boundaries

- Manifest V3 permissions: `cookies`, `nativeMessaging`, HTTPS YouTube host
  access, and split Incognito operation. No content scripts, login interception,
  broad site access, external server upload or extension-storage cookie values.
- Capture requires explicit extension consent, a matching pending operation and
  nonce, one uniquely identified active Incognito tab/store, and YouTube scope.
  Normal-store cookies and partitioned cookies are rejected, never flattened.
- Native host accepts only its fixed extension origin, bounded native-endian
  JSON framing and an allowlisted schema. Duplicate JSON keys, control-character
  injection, wrong IDs/nonces/stores and repeated transfers reject safely.
- The origin is enforced by Chrome's `allowed_origins` policy and checked by the
  helper. This is **not cryptographic protection against malicious software
  already running as this user** or a malicious replacement of the unpacked
  extension/source. Protect your local account and inspect extensions.
- Full captured cookie attributes remain in one macOS Keychain generic-password
  item: service `com.morgan.media-downloader.youtube-companion`, account
  `youtube-session-v1`, accessible while unlocked on this device. No credential
  CLI arguments, normal settings JSON or persistent plaintext cookie files.
- yt-dlp receives a fresh in-memory Netscape cookie stream for each context.
  Domain/path/secure/expiry/session attributes survive. Netscape/yt-dlp does not
  reproduce browser SameSite policy, and this yt-dlp version strips the HttpOnly
  marker while loading. Those browser-only attributes remain in the Keychain
  source; no JavaScript executes in yt-dlp. Partitioned cookies are unsupported.
- Pending nonce and import receipt under the private user application-support
  `companion` directory contain **no cookie values**. Capture is single-use;
  storage failure does not fall back to plaintext. Receipt polling never blocks
  the GUI waiting on the helper's Keychain lock.
- Python strings/cookie jars cannot guarantee secure zeroization. Already-running
  attempts may retain their in-memory snapshot until finished; Disconnect cannot
  remotely revoke Google sessions or erase another process's memory.
- Cookies are sent to YouTube as required by authenticated requests, not to an
  unrelated external service. OS Keychain access may require user approval.

## Watch Later and runtime fixes

Known Watch Later forms use configured authentication upfront in Auto rather
than waiting for a misleading “playlist does not exist” response. None remains
explicitly unauthenticated. Ordinary text/search and unrelated missing playlists
keep their existing policy. Successful companion capture selects the distinct
YouTube Companion mode; that mode never silently loads ordinary Chrome cookies.
Watch Later analysis cannot drop authentication on a format failure.

The observed `Urllib3PercentREOverride ... sub` error was reproduced offline with
yt-dlp **2026.08.19** and urllib3 **2.8.0**. Reloading app-managed yt-dlp modules
left yt-dlp's global urllib3 regex wrapper installed; the next import wrapped it
again. Its `__getattribute__` delegation bypassed the nested wrapper's dynamic
attribute fallback. The app now unwraps only that exact yt-dlp-owned wrapper to
an actual compiled regex before purging/reloading yt-dlp. No dependency downgrade
or modification of upstream code. A subprocess regression repeats real reloads
and parses URLs without network access.

## Disconnect and removal

**Disconnect** immediately deletes the captured Keychain item (even if settings
are later Cancelled), then immediately persists None for future tasks without
saving unrelated pending edits. Failed deletion is reported, never described as
success. If storage succeeds but settings persistence fails, Accounts distinguishes
the stored/deleted Keychain state from the still-applied authentication mode and
asks you to fix settings-folder permissions and retry Apply or Reconnect.

Terminal equivalents, from the repository root:

```sh
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.youtube_companion.setup status
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.youtube_companion.setup disconnect
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.youtube_companion.setup remove
```

`remove` deletes only the inspected host files and empty directories it owns;
adding `--development-launcher` explicitly includes an owned legacy launcher.
It does not delete the Keychain item implicitly. Run
`disconnect` first. In Chrome's extensions page, manually **Remove** the Morgan
extension. Control files contain no cookies; they may remain after removal, and
pending authorizations expire after five minutes. No broad user-folder deletion.

## Development launcher

The Desktop `.app` is a shell-based development launcher with an Info.plist,
not a compiled standalone distribution or signed/notarized release. It needs
this checkout, its working `.venv` and the external drive. Missing project/Python
produces a fixed explanatory macOS alert; third-party diagnostics are not copied
into a new plaintext launcher log. Run the source command above for diagnostics.
Automated tests exercise its executable and missing-drive failure; actual Finder
double-click/Gatekeeper behavior and live browser sign-in require manual checks.

## Tests

Use synthetic cookies and isolated application state, never a real browser DB:

```sh
test_root=$(mktemp -d /private/tmp/morgan-companion-tests.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
MORGAN_DATA_DIR="$test_root/data" MORGAN_LOG_DIR="$test_root/logs" \
MORGAN_CACHE_DIR="$test_root/cache" \
.venv/bin/python -B -m pytest -q -p no:cacheprovider
node --test companion/tests/core.test.mjs
.venv/bin/python scripts/check_backend_protocol.py
.venv/bin/python -m pip check
```

Most storage tests inject synthetic stores. On macOS,
`tests/test_companion_storage.py` additionally exercises the real Security.framework
save/read/replace/delete ABI using a uniquely named temporary synthetic Keychain
item, with OS UI prompts disabled and cleanup in `finally`. It never reads a
browser or Google account item. A sandbox can deny this test (observed OSStatus
100001); grant the test normal user Keychain access rather than skipping it or
weakening assertions. Other platforms verify the explicit unsupported-storage
error instead. This does not prove real session entitlement or interactive
Keychain consent behavior. Extension tests mock documented Chrome APIs. The
installed host can be tested with a synthetic framed `ping` without reading
cookies. Real Chrome capture, Keychain consent and private-media access must be
tested with the user's explicit participation. Swift migration, hosted
qualification and release packaging are outside this local feature.
