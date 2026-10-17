# Local authentication and UI refresh

Local branch: `improvement/auth-ui-refresh`, based on qualified Phase 2 commit
`b603921f92dcf5238e6451ba46346ebe450bedfb`. Swift source/CI and published branches
are not modified. This task does not implement Phase 3. Work remains local.

## Checkpoint A — account connection

Settings → Accounts → YouTube offers Connect, browser/profile detection,
Sign in using browser, Verify Connection and Disconnect. Connect selects the
existing Browser Cookies mode; Apply/OK saves the choice for existing analysis,
queue and download paths. Cancel leaves saved settings untouched. Disconnect
disables future cookie use after Apply; it does not log out the browser, revoke
Google sessions or alter running tasks. Reset restores existing Auto defaults.

Detection reads app locations and profile metadata only, including Firefox
profiles.ini. Cookie extraction/decryption remains yt-dlp's responsibility.
Safari/Firefox/macOS access can require user permissions; discovery is not proof
that a database is readable. Browser sign-in opens the selected installed browser;
the user must select the same profile there. No incognito export, app-owned
browser profile, Qt WebEngine or Google password form is added.

Verification is intentionally different from Auto extraction: it explicitly tests
the configured fallback cookie source while Auto download behaviour stays
public-first. It reads the in-memory yt-dlp cookiejar, then a bounded YouTube
account page and a strictly boolean LOGGED_IN server configuration. Missing page
configuration is unconfirmed, never authenticated. No playlist/history entries
are enumerated or displayed. A server-confirmed session is **not proof of private
playlist ownership, entitlement, working formats or PO-token readiness**. Those
are checked by the existing extraction/download paths. None mode tests public
connectivity only. Verification does not rewrite imported cookie files.

Results distinguish readable/missing cookies, signed-out/rejected sessions,
rate limiting, additional verification, provider requirements and unavailable
connections with fixed safe text. Browser/profile/file/network edits invalidate
verification; stale task results cannot overwrite the new state. Network tests
now use the selected Direct/System, custom HTTP/SOCKS5h or available Tor route,
including configured proxy credentials without displaying them. Verification
does not start Tor, rotate circuits or fall back to Direct on routing failure.

### Embedded browser feasibility and references

Google restricts embedded user agents at its authentication endpoint. Qt
WebEngine cookies are not a supported yt-dlp cookiesfrombrowser source; exporting
an embedded/guest jar would introduce session handling and still not prove Google
sign-in works. A dedicated external profile is technically a separate option,
but would introduce profile lifecycle/locking/cleanup without removing the need
for browser permissions. This implementation uses existing supported browser
profiles, with explicit user-controlled Netscape cookies.txt import as fallback.
It never exports all browser cookies or uses an OAuth-to-yt-dlp conversion.

- [Google embedded-agent restrictions](https://developers.google.com/youtube/reporting/guides/authorization/server-side-web-apps)
- [Upstream YouTube cookie and OAuth guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- [Apple sidebar guidance](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Downie workflow/interface reference](https://software.charliemonroe.net/downie/)
- [Transmission utility reference](https://transmissionbt.com/)

## Verification boundaries

Automated checks use synthetic cookies, profile metadata and mocked network
responses only. No personal browser cookie database or Google account is read
by tests. A live authorised Mac check is still needed for browser permissions,
site-response changes, private-resource access and downloaded output. Do not
describe offscreen screenshots as Finder/Accessibility or live-account QA.

No new runtime dependency is required. Existing PyInstaller source discovery
includes the new Python modules; there is no WebEngine dependency.

## Checkpoint B — presentation

The five existing top-level routes now use a compact keyboard-accessible sidebar
(⌘1–5); menus and programmatic navigation keep their existing destinations.
Shared widgets live in ui_components.py, and theme.py supplies semantic Qt
palettes for System/Light/Dark without replacing the platform's native style.
Settings pages have bounded-width, scrolling forms. Accounts gives the main
connection actions priority and moves technical mode/import/reset controls into
an advanced disclosure. No saved settings schema was changed.

Download has stronger action hierarchy, drag feedback, readable candidate rows,
common options above the preview and persistent selection actions. A regression
test guards against the previous small-window splitter crushing option controls
to zero height. Advanced media controls remain reachable through More Options.
Queue/history tables have consistent spacing, alternating rows and useful empty
states; existing job IDs, multiselection, progress widgets and database paths
remain intact. Console retains its filters, fixed-width diagnostics and exports.

Private analysis errors expose account recovery and explicitly requested redacted
technical details, without an unauthenticated format retry. Queue authentication
failures link to Accounts. A subsequent explicit Retry/Resume of an auth-failed
media job adopts the applied account configuration only; other captured options,
unrelated failures, pending jobs and active tasks remain unchanged.

## Local validation and commands

Checkpoint A's full isolated offscreen Python suite passed **298 tests**. Later
Checkpoint B's final full suite passed **310 tests in 7.26s**, with no skips, on
17 October 2026 (Python 3.12.13, PySide6 6.11.2, yt-dlp 2026.08.19).
`pip check` reported no broken requirements, and the unchanged Python/Swift
protocol drift check passed. The normal app.main entry point is covered by a subprocess test
with isolated state, a timed graceful close, and only the external provider
probe/browser metadata replaced by fixtures. It is not live-account validation.

Source launch, from the repository:

```sh
cd "/Volumes/My Passport/Morgan/Documents/Coding/mediagrabber"
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader
```

Deterministic test command:

```sh
local_refresh_test_root=$(mktemp -d /private/tmp/morgan-ui-tests.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
MORGAN_DATA_DIR="$local_refresh_test_root/data" \
MORGAN_LOG_DIR="$local_refresh_test_root/logs" \
MORGAN_CACHE_DIR="$local_refresh_test_root/cache" \
.venv/bin/python -B -m pytest -p no:cacheprovider
```

Offscreen before/after artifacts are ignored under .tools/ui-review/. To reproduce
the after views without a real browser, private media or application user state:

```sh
PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python \
  scripts/capture_local_ui.py --output .tools/ui-review/after-light --theme Light
PYTHONPATH=src QT_QPA_PLATFORM=offscreen .venv/bin/python \
  scripts/capture_local_ui.py --output .tools/ui-review/after-dark --theme Dark
```

`before/` captures the old tab/form presentation after Checkpoint A;
`after-light/`, `after-dark/` and `after-small/` capture the refreshed widgets.
The small layout was checked at 900×650. All use synthetic media and isolated
state, not live extraction. Source visuals were inspected; native Mac appearance
and accessibility are still manual gates. Review found no Important/Critical
issues; minor stale-tooltip, diagnostic-access and source-specific recovery
wording findings were corrected and regression-tested.

**Packaging is currently blocked on this Mac.** An isolated direct PyInstaller
6.22.3 attempt collected auth/theme/ui_components successfully and built the
Python archive, but arm64 bootloader conversion invoked Apple lipo and failed
with exit 69 (unaccepted Xcode licence). No finished .app was produced. No sudo,
xcodebuild, xcrun or licence acceptance was run. Do not retry that known blocked
path locally; do not present build_macos.sh as a verified licence-free rebuild.
Packaging remains for an authorised builder, separate from source launch. The
existing PyInstaller spec/build scripts were not bypassed or rewritten.

Manual Mac checks still required: native widget appearance/focus/VoiceOver,
live system appearance changes, each installed browser's cookie permissions,
Google account-page compatibility, authorised private/Watch Later access,
selected proxy/provider downloads and packaged Finder/Gatekeeper launch. An
unknown verification response intentionally remains unconfirmed.
