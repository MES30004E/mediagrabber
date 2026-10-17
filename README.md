# Morgan Media Downloader

Morgan Media Downloader is a local, privacy-conscious macOS GUI for downloading media that you are authorised to save. It uses the **yt-dlp Python API** for structured analysis and progress updates, SQLite for a persistent queue/history, and PySide6 for a native desktop interface.

The main window includes Download, adaptive Queue, History, live Console, and Settings in a keyboard-accessible sidebar (Command-1–5). Media failures retain extractor, stage, playable-format, authentication, connection, and retry context; optional subtitle or thumbnail failures complete with persistent, visible warnings instead of hiding the usable media result.

The default `macOS / QuickTime` compatibility profile prefers H.264/avc1 plus AAC/mp4a sources before download, then uses bundled ffmpeg only when a stream needs conversion. Final MP4 output is fast-started and checked with bundled ffprobe for container, codecs, pixel format, subtitles, artwork disposition, and unintended streams. `Universal` uses the same broadly compatible baseline; `Original / Best Available` preserves source formats such as VP9, AV1, Opus, WebM, or MKV.

`File → Convert Media…` is a general local converter for MP4, MOV, M4V, MKV, and WebM. It offers macOS/QuickTime, Universal, Small File, Original/Remux, and Custom profiles; selectable H.264, HEVC, VP9, AV1, AAC, MP3, Opus, and FLAC codecs; container-aware subtitle handling; quality, resolution, frame-rate, bitrate, metadata, chapter, and artwork controls. It analyses streams first, blocks invalid copy/container combinations, copies compatible streams, transcodes only what changed, writes through a sibling temporary file, and requires final ffprobe verification before completion or replacement. Completed Queue and History entries provide both `Convert for macOS / QuickTime` and `Convert As…`.

Managed Tor uses an isolated app-owned data directory, OS-assigned localhost SOCKS and ControlPort listeners, and Tor cookie authentication. It explicitly avoids Tor Browser's 9150/9151 ports (and 9050/9051), publishes the current session endpoints in Settings and Details, and retries a launch collision up to three times. `New Tor Circuit` sends `SIGNAL NEWNYM` to that owned process, honours Tor's cooldown, rechecks the exit IP without assuming it changed, and never reads or modifies Tor Browser's profile. Target-specific automatic retries are limited to three and always restart extraction from the original URL.

The application does not decrypt DRM, bypass account permissions, or download Spotify's encrypted streams. Authenticated YouTube access uses only yt-dlp's supported cookie mechanisms. Spotify links are resolved as public metadata where available, converted to `artist + title` searches, and shown as ranked YouTube candidates for explicit user selection.

## Build and launch

Source requirements: macOS 12 or newer and a user-local Python environment. No administrator password, Homebrew, or global Python packages are needed for source launch. Packaging has additional Apple-tool requirements: on this owner's Mac, PyInstaller's `lipo` step is licence-gated, so the build commands below are **not currently usable locally**. Do not accept the Xcode licence or retry them to validate UI changes; use source launch instead. See [local validation notes](docs/LOCAL_AUTH_UI_REFRESH.md#local-validation-and-commands).

This repository is the existing Python/PySide6 baseline, not a Swift rewrite. Start with [docs/CODEX_CONTEXT.md](docs/CODEX_CONTEXT.md) and [docs/CURRENT_ARCHITECTURE.md](docs/CURRENT_ARCHITECTURE.md) before changing it. Initialise the pinned provider submodule after cloning:

```sh
git submodule update --init --recursive
```

```sh
./build_macos.sh
open "dist/Morgan Media Downloader.app"
```

The script:

1. Creates a copy-based project-local Python 3.12 `.venv` using a durable user-local `uv` interpreter (and downloads `uv` into `.tools` only if needed). The interpreter must not live in temporary storage; exFAT volumes cannot host uv's interpreter symlinks.
2. Installs dependencies only into `.venv`.
3. Downloads architecture-matched `ffmpeg` and `ffprobe` into `resources/bin`.
4. Runs the complete unit test suite.
5. Builds `dist/Morgan Media Downloader.app` with PyInstaller.

The resulting app is architecture-specific. Build once on Apple Silicon for arm64 and once on an Intel Mac for x86_64; a universal bundle is intentionally not synthesized from mismatched Python/Qt binaries.

Native media binaries and distribution bundles are deliberately not committed. The normal build downloads ffmpeg/ffprobe, but does **not** build or download aria2c. To package the torrent engine, obtain a trusted architecture-matched aria2c separately; the existing arm64 build provenance is retained in [resources/bin/ARIA2_PROVENANCE.md](resources/bin/ARIA2_PROVENANCE.md). `scripts/build_aria2c_macos.sh` requires an authorised native compiler toolchain and must not be run on the licence-restricted local Mac. A fresh clone can develop/test Python without rebuilding aria2, but media integration tests need compatible ffmpeg/ffprobe binaries.

The local development Mac cannot accept the Xcode licence. Do not run Xcode, `xcodebuild`, `xcrun`, sudo, or licence acceptance there. Source development is not blocked by that restriction. The packaging script is not a prerequisite for development, and a passing test suite is not proof of a current packaged build.

## Features

- URLs, multi-line input, playlists/collections, YouTube Music, text search, and drag/drop
- One-click Download/Download All with internal independent analysis, plus optional cancellable Analyse/Analyse All previews
- Structured yt-dlp analysis, progress hooks, fragment progress, speed, ETA, and postprocessor state
- Background stable yt-dlp updates from official GitHub releases, with SHA256 verification, user-local versioned activation, rollback, and a permanently bundled fallback
- Video quality/container and audio conversion settings, subtitle/metadata/thumbnail options, editable filename templates
- Select-all, select-none, and invert-selection playlist/match table
- Persistent SQLite queue and local searchable history
- Two concurrent downloads by default (configurable from one to four)
- Pause/resume via yt-dlp partial files, cancel, retry, open, reveal in Finder, and clear-completed controls
- Direct, HTTP proxy, SOCKS5H proxy, External Tor, Managed Tor, and system/Proton VPN modes
- A prominent main-screen connection selector shared with the visible Settings tab and the standard Command-, Settings action
- Tor Browser endpoint discovery at `127.0.0.1:9150`, then `127.0.0.1:9050`
- Managed Tor launches only Tor's executable, reserves a fresh localhost SOCKS/Control pair for each session, uses an isolated application data directory, and tracks only its owned process
- Bounded transfer/fragment retries with exponential backoff, plus up to three app-owned Managed Tor circuit retries for classified target rejection (an existing policy requiring separate review)
- HTTP PO-token provider health check at `/ping`, configurable provider URL, and Node/Deno script fallback discovery
- Auto authentication (public media first without cookies), genuine yt-dlp browser-cookie extraction for Chrome, Chromium, Firefox, Safari, or Edge profiles, plus in-place Netscape `cookies.txt`
- One-time unauthenticated recovery when account cookies cause a public video's format list to become unusable; private/account-required media never drops authentication
- Atomic selectable-subtitle muxing: valid media first, optional sidecar acquisition, temporary ffmpeg mux, ffprobe stream/language verification, then atomic replacement
- Async thumbnail preview with safe extractor headers, loading progress, bounded cache cleanup, plus independent embedded-artwork verification
- Redacted 10,000-line live Console with source, warning/error, and per-job filtering
- Media/Torrents/All adaptive Queue layouts, job-ID-bound selection/details that survive live progress refreshes, persistent warning details, and classified failure-stage diagnostics
- Strict Pause/Resume/Retry/Restart semantics and persisted per-job final, partial, temporary, subtitle, and thumbnail file inventories
- Lawful `.torrent` and magnet input, metadata/file selection, and queue integration through the bundled native arm64 `aria2c`
- Auto/never/always collection subfolders with duplicate-root prevention and macOS-safe names
- Crash recovery marker and persisted running jobs restored as Interrupted instead of silently resumed
- First-run checks for yt-dlp, ffmpeg, ffprobe, output permissions, bgutil, Tor Browser, Managed/External Tor, and aria2c
- Rotating local logs under `~/Library/Logs/Morgan Media Downloader/` (five files maximum)
- Atomic settings at `~/Library/Application Support/Morgan Media Downloader/settings.json`

## bgutil PO-token provider integration

The existing `bgutil-ytdlp-pot-provider/` repository is an upstream submodule pinned at `7608dd51ee813b48cf9a6d68c6e42cb197ce10e0` (1.3.1). Its implementation is not rewritten. Source-mode discovery adds the plugin directory to Python's import path; the PyInstaller specification includes the plugin source and hidden imports. The normal build does not separately pip-install that plugin.

Discovery order:

1. Check the configured HTTP endpoint (default `http://127.0.0.1:4416/ping`).
2. If unavailable, look for a configured script-provider server folder.
3. Look for `MORGAN_BGUTIL_HOME/server`.
4. Look for the repository beside this project or at `~/bgutil-ytdlp-pot-provider/server`.

If both modes exist, yt-dlp's provider preference keeps HTTP first. The app passes the selected download proxy to yt-dlp; the unmodified bgutil provider then passes that request proxy into HTTP or script PO-token generation. Custom SOCKS and Tor URLs use `socks5h`, preserving remote DNS resolution.

Node 20+ or Deno 2+ is needed only for script-provider fallback. Managed Tor uses a separate data directory and never modifies or launches the Tor Browser GUI. The app never starts or reconfigures the bgutil server automatically.

The submodule does not include generated server `build/` or `node_modules/` content. Follow its own `server/README.md` for dependency installation and compilation when script/HTTP server operation is needed. Merely discovering a source folder and JS runtime does not prove token generation works.

Tor Browser defaults to `~/Applications/Tor Browser.app` when present, otherwise `/Applications/Tor Browser.app`. An explicitly saved path is preserved; choose a different location in Settings when needed.

## Authentication

Use **Settings → Accounts → YouTube → Connect YouTube**, select the signed-in
browser/profile, optionally open that browser to sign in, then **Verify Connection**.
Apply saves the configuration for future operations. Disconnect disables cookie
use after Apply without logging out the browser or changing active tasks. Manual
cookies.txt import/reset remain under Advanced authentication. The verification
result separates readable cookies from a server-confirmed session; missing or
changed response evidence is unconfirmed. A valid session does not prove permission
to a particular private resource or that download/provider requirements are met.
Auto downloads remain public-first. See [local refresh notes](docs/LOCAL_AUTH_UI_REFRESH.md)
for workflow, test boundaries, screenshots and packaging limitations.

Authentication is independent from PO-token and proxy configuration. A YouTube job can simultaneously use browser cookies or an imported Netscape cookie file, the bgutil provider, and the selected HTTP proxy/Tor connection. Cookie values are never displayed or logged, and the app does not inspect browser cache files itself.

Watch Later accepts `:ytwatchlater` unchanged, `https://www.youtube.com/playlist?list=WL`, and the `/feed/watch_later` browser route. Explicit Watch Later URLs on `youtube.com`, `www.youtube.com`, `m.youtube.com`, and `music.youtube.com` normalise to the canonical HTTPS `playlist?list=WL` URL; scheme-less versions of those routes also work. Ordinary playlist URLs and `watch?v=...&list=WL` are passed through without rewriting. Ordinary text still becomes a YouTube search.

Watch Later/private collections need an account authorised to access them. Choose Browser Cookies or Imported cookies.txt explicitly when Auto does not recognise the site's authentication error. Parsing support does not prove live account access. Never commit cookie files, browser exports, or local cookie paths. See the [official yt-dlp cookie FAQ](https://github.com/yt-dlp/yt-dlp/wiki/FAQ) for supported authentication and export security guidance.

`Auto` is the default: public YouTube extraction begins without account cookies. When YouTube explicitly requires authentication, Auto retries with the selected browser profile. Explicit Browser Cookies and Imported cookies.txt modes use yt-dlp's `cookiesfrombrowser` and `cookiefile` Python parameters. If authenticated extraction of otherwise public media returns no usable formats, the app retries once without authentication and records the safe effective mode. Settings includes the exact `https://www.youtube.com/robots.txt` cookies.txt export guide.

Restart is intentionally different from Resume and Retry. Resume/Retry retain job-owned `.part`/`.ytdl` state; Restart waits for the worker, deletes only paths in that job's inventory, resets transfer metrics, and starts again. Remove offers list-only retention or deletion of recorded files, moving completed output to the user's Trash where practical. Unrelated files and unverified directory contents are never wildcard-deleted.

## Torrents

BitTorrent is handled by a separate aria2c process, never by yt-dlp. The app accepts user-supplied `.torrent` files and magnet links but contains no torrent search or discovery feature. Torrent connections are limited to Direct or System / Proton VPN; Tor is intentionally not offered for peer traffic. The app prefers its bundled native arm64 aria2c, then a user-selected executable, then a user-local PATH executable. It does not depend on Homebrew.

For public torrents, embedded/magnet trackers, DHT, IPv6 DHT, PEX, and optionally Local Peer Discovery are enabled according to Settings. Optional extra public trackers are off by default, deduplicated, and never added to private torrents. A private flag forces DHT, IPv6 DHT, PEX, LPD, and extra tracker injection off. Queue status parses aria2's console readout: `CN` is shown as connected peers and `SD` as connected seeders; tracker swarm estimates are not fabricated or relabelled.

## Spotify behavior and limitations

For a public Spotify track, the app queries Spotify's public oEmbed metadata endpoint, creates an `artist title` search, scores candidates using text and duration (when duration exists), and displays match confidence. The user selects the actual yt-dlp-supported source to download.

Public oEmbed does not reliably expand every track in an album or playlist. Full Spotify collection expansion therefore remains unavailable unless a future version adds an explicitly configured, authenticated Spotify Web API client. The app does not scrape/decrypt Spotify streams as a fallback.

## Privacy and security

- No `shell=True`; user input is never interpreted as a shell command.
- History stays in local SQLite and is never uploaded.
- Proxy passwords are stored in macOS Keychain when supplied and are never written to settings JSON.
- Logs redact messages containing cookie/password/token markers.
- Browser cookies are handed directly to yt-dlp's supported browser-cookie mechanism and are not logged.
- Downloads are written only to the user-selected folder.

The app bundle is ad-hoc/local and is not notarized. On another Mac, Gatekeeper may require the normal user confirmation for an app downloaded from the internet; no admin rights are required.

## Development

```sh
uv python install 3.12.13 --no-bin
build_python=$(uv python find 3.12.13)
"$build_python" -m venv --copies .venv
.venv/bin/python -m pip install --only-binary=:all: -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader
```

Core modules are under `src/morgan_media_downloader/`; tests mock or avoid external downloads.

Stage 1 verification on 1 October 2026: Python 3.12.13, pytest 8.4.2, yt-dlp 2026.08.19, PySide6 6.11.2; **222 tests passed**. This is a dated local test result, not a guarantee for future dependency versions or live sites. No app packaging, native compilation, or private-account QA was performed. Dependency ranges are not yet a reproducible lockfile.

## Known incomplete items

- Spotify album/playlist expansion without user-provided official API credentials
- Full live authentication/Watch Later QA; Auto still recognises account-required errors by message substrings. The new bounded account-page check may remain unconfirmed when Google changes its response.
- Native visual/accessibility and live browser-permission QA; current UI evidence is offscreen Qt with synthetic media. Local PyInstaller packaging is blocked by licence-gated Apple lipo; source launch and tests do not require it.
- Review one-click Spotify downloading: the preview supports match selection, but direct Download can enqueue all candidate matches
- Converter cancellation, concurrent stderr draining, and explicit destination-overwrite confirmation
- Advanced extra-safe-options and Console-detail settings are currently stored but not operationally applied
- Fresh-clone aria2 acquisition and reproducible dependency/tool checksums
- Live private YouTube content still requires a user-controlled account test; automated QA never reads or prints cookie values
- macOS code signing/notarization and a combined universal2 release
- Full live-site QA depends on remote service and legal test-swarm availability; deterministic automated tests mock external downloads

## Third-party components

The build bundles PySide6/Qt, yt-dlp, the existing GPL-licensed bgutil provider plugin, GPL static `ffmpeg`/`ffprobe` builds from the `eugeneware/ffmpeg-static` release, and aria2 1.37.0 built from the official release source. aria2 source and binary checksums are recorded in `resources/bin/ARIA2_PROVENANCE.md`. Review each dependency's license before redistribution.

The packaged app is never modified by its updater. Verified yt-dlp releases are stored under `~/Library/Application Support/Morgan Media Downloader/runtime/yt-dlp/`; the updater does not inspect `PATH`, invoke Homebrew, or require administrator access.

Keep this baseline private unless public publication is explicitly approved. No application-level licence has been chosen; upstream licences and redistribution obligations still need review. `.gitignore` is a safety layer, not a substitute for reviewing the staged file list and diff.
