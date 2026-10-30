# MediaGrabber feature backlog and qualification ledger

Updated 2026-10-30. This extends, rather than replaces, the Reliable Downloads,
Better UX and Public Releases master goal. The Critical UX, Scalability and
Architecture Addendum changes the implementation order below. An existing helper,
passing unit test or metadata inspector is not evidence of a finished feature.

## Current checkpoint and restrictions

- Development branch: `improvement/download-reliability`. Latest hosted-tested
  checkpoint: `90e3d3b0dd84da1ad47079c6c3474c4780a3ed27`, run `41031238079`,
  all jobs passed. Actual logs: Linux631; macOS backend60, Swift25 and protocol9;
  bundled provider/media, Cocoa startup/clean shutdown, replacement backup and
  strict extracted-archive verification/launch passed. Archive141681058bytes,
  SHA256 `633363e747365d6299121329aa896471db8c36e3526005910a53227f5a5f7adf`.
  No release asset was uploaded or installed.
- Earlier Canvas failure (`40989481899`, extracted `ImageData.o`) was fixed by
  staging only the required `canvas.node` before normal signing (`9a06044`).
  Strict signature verification was not bypassed. Later green runs include this
  fix, atomic admission (`223737b`), bounded status actions (`d5b3365`) and
  keep-files removal (`90e3d3b`). Detailed evidence remains in QUEUE_SCALE.md.
- New asynchronous owned-file removal checkpoint: **646 Python tests passed
  in22.62s**, JS10/protocol9 matched, pip check clean. FileRemovalService admits
  one owned worker with at most32 copied jobs; GUI owns persistence and counts.
  Stop immediately reports pending work, finishes the admitted slice and stops
  future slices. Partial filesystem/DB failure retains entries; shutdown retains
  uncertainty evidence and still drains workers after a marker-persistence error.
  Entire confirmed removal snapshots supersede earlier pending restarts.
- Synthetic cleanup100/800/1,000/5,000 probes pass with one confirmation, one
  cleanup worker and zero GUI cleanup calls; no actual user files touched.
  Latest source needs its own hosted qualification. Native crash classification,
  real Trash/cross-volume QA, model/view memory, bulk restart and collections
  remain unfinished; no broad crash/scale/release acceptance is implied.
- Preserve all existing edits and the unrelated October 4/18 migration drafts.
  Main remains `6a024ec97d2521beed1c6cce2752aaa605425390`; qualified Swift bridge
  remains `b603921f92dcf5238e6451ba46346ebe450bedfb`. No Swift Phase 3 work.
- Provider stays pinned at `7608dd51ee813b48cf9a6d68c6e42cb197ce10e0` (1.3.1).
- No local Xcode, xcodebuild, xcrun, sudo, licence acceptance, Homebrew or signing/
  packaging builds. Native qualification uses hosted macOS. No personal cookies,
  Keychain exports, live private playlists or private-media automated tests.
- Before every push: scan all app refs/reflogs/history, provider history and the
  exact index; triage every finding; verify Public repository metadata. No force
  push, merge to main, tag, release/asset publication or installation without the
  required explicit approval. Preserve the existing icon.
- Installation remains unresolved by user choice. Preserve the preferred external
  `dist` requirement; the latest addendum names `dist/MediaGrabber.app`, whereas
  the existing bundle is `Morgan Media Downloader.app`. No rename or alternate
  launcher is approved/implemented here. My Passport is exFAT; current framework
  symlinks require an explicitly resolved compatible deployment approach.

Status vocabulary: **Partial** = useful implementation, not full acceptance;
**In progress** = unfinished worktree; **Open** = not implemented/qualified;
**Release blocker** = must pass before distribution; **Portable-tested** or
**Hosted-tested** always states the limited evidence, not universal compatibility.
Paths below are repository-relative; each row retains its own remaining QA.

## P0: queue scale, crashes and proper batch operations

| ID / status | Acceptance criteria | Related code/tests now | Remaining work / QA |
| --- | --- | --- | --- |
| Q01 Release blocker; narrow stall fixed | Synthetic 100/800/1,000/5,000-item analysis/enqueue/start/pause/cancel/remove/reload runs; classify exception/native fault/OOM/unbounded work from evidence | `scripts/benchmark_queue.py`, `test_queue_scale_probe.py`, `docs/QUEUE_SCALE.md`; existing UI/task tests | Before800 stalls15s and5,000 times out120s; after allfourcomplete,800pause/resume/cancel0.065/0.071/0.067s. No native crash reproduced;5,000enqueue still1.3s gap/~407MiB. Model/service/backpressure and active/race/native QA remain |
| Q02 Portable-tested fix | Removing 800 selected jobs opens at most one confirmation, shows actual total and running/completed counts; Cancel changes nothing | `ui.py:remove_selected`, `_confirm_remove`; `test_queue_bulk.py` | One selected-ID snapshot/one native dialog, keep-files default, latest post-modal inventory and deferred active-removal tests now pass; native visual/realactive QA remains |
| Q03 Partial; bounded worker connected | Default keeps files; optional deletion touches only verified job-owned paths; no wildcard destination deletion | `file_ownership.py`, `file_removal.py`, `ui.py`; ownership/service/bulk tests | One explicit decision;32 snapshots/one owned worker after transfer owners stop; successful cleanup precedes atomic DB removal. Temp-owned/foreign, stop/admission/DB/close failures tested; real Trash, cross-volume and realistic transfer races remain |
| Q04 Open | Select all/none/visible/filtered; select waiting/running/completed/failed/paused/cancelled jobs | `ui.py` queue table/filter and `_selected_jobs` | Queue selection is not the analysed-playlist checkbox selection; implement and test each action and stable selection across refresh/filter |
| Q05 Partial; bounded status/removal connected | Pause/resume, cancel selected/collection, retry failed/selected, safe restart and removal remain asynchronous/bounded; report completed/failed/pending counts | `queue_batch.py`, `file_removal.py`, `ui.py`, `tasks.py`; batch/bulk/service tests | Status/retry and entry/file removal now yield with correlated outcomes and800-job regressions. Bulk restart still per-item; collection controls, real transfers and broad shutdown/crash qualification remain |
| Q06 Open | Clear collection, completed/cancelled and failed entries with safe default and one confirmation | `Database.clear_completed`, queue actions | Discoverable group-level actions, tested counts and no per-item modal loop |
| Q07 Open | Collection grouping, group progress/status totals and bulk controls remain responsive | `models.py`, `ui.py`, `database.py` | Define persisted collection identity/migration; incremental aggregate/model updates; restart compatibility tests |
| Q08 Open | Stable extractor/media identity deduplicates queue/download archive; completed outputs are not accidentally redownloaded or destroyed | `models.py`, `downloader.py`, `database.py`, `organisation.py` | Explicit duplicate/archive policy, cross-URL identities, missing outputs, retries and deliberate restart tests; no assumed guarantee from UUID job IDs |
| Q09 Partial | Interrupted jobs restore accurately; resume preserves compatible partials and completed outputs | `Database.load_jobs`, `downloader.py`, `file_ownership.py`; `test_database.py`, `test_downloader_policy.py` | Scale/relaunch tests, transactional bulk persistence and fault injection across cancellation/removal/shutdown |
| Q10 Partial | Batch quality/container/audio/subtitle defaults plus per-item overrides survive queueing/restart | `models.py`, `media_details.py`, `ui.py`; `test_media_details.py`, `test_media_details_ui.py`, `test_formats.py` | Existing media-selection coverage is not queue-wide batch edit; test mixed sources, unsupported requirements and large selected sets |
| Q11 Release blocker | Memory/worker/network queues stay bounded and UI interactive under 800 jobs; rate-aware retries, no retry storm | `tasks.py`, `ui.py:_dispatch`, `_refresh_queue`, downloader callbacks, thumbnails | Instrument before changing architecture; model/view where justified, dirty-ID updates, signal coalescing, bounded work and batch DB transactions; report measured deltas |

## P1: professional native UX, architecture and real media viewing

| ID / status | Acceptance criteria | Related code/tests now | Remaining work / QA |
| --- | --- | --- | --- |
| U01 Open | `docs/UI_DESIGN_SYSTEM.md` defines navigation, type, spacing/density, light/dark tokens, contrast/focus, controls/tables/progress/menus, states, resizing/fullscreen and destructive patterns | `theme.py`, `ui_components.py`, `ui.py`, `settings_window.py` | Research Stacher 7/ClipGrab interactions and Apple/Qt authoritative guidance; create actual mockups/screenshots before large redesign; user design approval |
| U02 Open | Real compact/standard/large/fullscreen screenshots in light/dark show readable, aligned unclipped UI; retain icon/native PySide6 | `test_playlist_workspace.py`, `test_settings_window.py`, `test_ui_refresh.py` | Offscreen pass is not visual acceptance. Capture/inspect real application; document exact image paths and manual native fullscreen QA; no casual web rewrite |
| U03 Partial | Large analysed playlist has resizable remembered panels, collapsible options/preview, search, visible/all/none/invert, counts, keyboard/multi-selection | `ui.py`, `settings.py`; `test_playlist_workspace.py`; `docs/PLAYLIST_WORKSPACE.md` | 800–5,000 scale qualification and visual QA; current playlist table is still item-based |
| U04 Partial | Lazy playlist thumbnails and real duration reflect current selected video, avoid N requests and route fallback | `thumbnail_cache.py`, `ui.py`; `test_thumbnail_cache.py`, `test_playlist_workspace.py` | Distinct from viewer: real rendered thumbnail/duration QA, scrolling/large-list responsiveness, missing/slow/cancelled responses |
| U05 Partial | On-demand per-video format/audio/language and manual/automatic subtitle metadata; only available controls; safe overrides | `media_details.py`, `media_details_dialog.py`, `formats.py`, `subtitle_mux.py`; media-details/formats/subtitle tests | Real authorised media and batch language/subtitle outputs with explicit user participation; no invented Original/default identity or 800 automatic inspections |
| V01 Open | Discoverable downloaded-media grid/list with thumbnails/metadata, search/filter/sort/browsing history and Finder open/reveal | History currently offers Open/Reveal; `ui.py:_history_context_menu` | Build actual library/viewer; Inspect Video is metadata, **not playback**; add index/model and missing-file tests |
| V02 Open | Actual video/audio playback, play/pause/seek/volume/fullscreen, duration/timeline, available audio/subtitle choice | No qualified in-app playback implementation | Evaluate QMediaPlayer/QVideoWidget, packaged backend/codecs and safe external-player fallback; explicit user validation on real local media and packaged app; unsupported errors truthful |
| A01 Open/incremental | Separate presentation/models, queue/batch service, execution/scheduling, auth/session, inspection/playback, persistence, updates and diagnostics with clear ownership | Existing separated downloader/auth/database/tasks/update helpers | Debt register below; refactor only measured/reproduced problems, preserve DB compatibility and existing behavior, use typed/testable boundaries; no whole-project rewrite or unproved deletions |

## Download reliability and authentication (original highest-priority goal retained)

| ID / status | Acceptance criteria | Related code/tests now | Remaining work / QA |
| --- | --- | --- | --- |
| D01 Partial; live unverified | Authenticated individual extraction/download succeeds independently of flat playlist analysis | `downloader.py`, `yt_runtime.py`; `test_player_failure.py`, `test_downloader_diagnostics.py`; `docs/DOWNLOAD_RELIABILITY.md` | Upstream authenticated-player failure strongly matched; isolated verified nightly/provider imports qualified, **not** a live-account reproduction. User must explicitly validate authorised video, transfer and playback |
| D02 Portable-tested | Explicit auth preserved through analysis/format refresh/download/subtitles; no silent anonymous fallback; bounded HTTP403 refresh; precise stage/category | `auth.py`, `downloader.py`; `test_auth.py`, `test_player_failure.py`, `test_downloader_policy.py` | Verify live provider/token/player/format/transfer distinctions with user; retain one-retry bound, compiled per-item selectors and fresh IDs |
| D03 Partial | Nightly reversible and separate from stable; JS/player runtime and pinned provider compatible | `yt_runtime.py`, `provider.py`; `test_yt_runtime.py`, `test_javascript_runtime.py`; runtime docs | Provider import is not generation success. Requalify runtime changes; stable remains rollback option; no unattended nightly activation |
| AU01 Partial | Accounts truthfully separates extension/native host, consent, transfer, Keychain, verification, identity confirmation and downloader/provider readiness; redacted times/errors/recovery | `settings_window.py`, `youtube_companion/`, `keychain.py`; companion/storage/connection/settings tests; auth docs | Real browser/manual Incognito, Keychain session and user download acceptance; never invent account/channel identity |
| AU02 Portable-tested | Successful managed import persists/activates only auth settings, without unrelated Apply; Cancel remains meaningful | `settings_window.py`, `youtube_companion/bridge.py`; `test_youtube_connection.py`, `test_settings_window.py` | Real UI workflow verification; nonce TTL/single-use/ownership and secure local storage remain required |

## P2: multi-site, site-scoped privacy and first-run onboarding

| ID / status | Acceptance criteria | Related code/tests now | Remaining work / QA |
| --- | --- | --- | --- |
| M01 Partial foundation | yt-dlp Python API supports feasible single URLs/playlists/channels/collections/generic embedded sources/audio/quality/languages/subtitles/batch/archive; truthful unsupported/auth/DRM errors | `parsing.py`, `downloader.py`, `formats.py`; parsing/downloader/format tests | Research current official extractor capabilities and competitor workflows; representative controlled fixtures/site matrix, no universal-site/DRM-circumvention/Spotify encrypted-streaming claims |
| M02 Open site scoping | Separate anonymous, YouTube Companion, supported browser-profile and Netscape imports; future consented domain-scoped capture; OAuth only officially supported | `auth.py`, `youtube_companion/`; existing auth/companion tests | Site-scoped account/session model, least-privilege extension domains, synthetic cross-domain/profile isolation tests; never forward cookies to unrelated domains or silently switch profiles |
| M03 Open lifecycle choices | Session-only in memory clears on exit; Remember securely in Keychain has expiry/reverification/Disconnect; No auth attaches none | Existing YouTube Keychain/session storage is not a generic site-account system | Implement lifecycle/isolation per site, loaded/verified/rejected/expired/missing states without values; no cookie paste/DevTools extraction instructions |
| M04 Partial routing; privacy QA open | Auth and network choice independent; consistent authorised Tor/proxy routing; personal login explicitly not anonymous; no silent Direct or circuit-rotation bypass | `network.py`, `managed_tor.py`, `auth.py`, `thumbnail_cache.py`; network/Tor tests | Inspect existing retry/circuit behavior against addendum, clear warning and explicit route-switch approval, synthetic routing/credential leak probes; real Tor/account use only explicit user validation |
| F01 Open | First-run guides runtime, FFmpeg/probe, Companion/native host/manual Incognito, capture/verification, destination and optional network | `diagnostics.py`, Settings/Accounts tools; setup/diagnostics tests | Cohesive first-run flow and packaged new-user QA. No Terminal/Python/Git needed by ordinary qualified-release users; browser-only steps remain manual |
| M05 Retained boundary | Spotify metadata→artist/title search→user-reviewed lawful source matches; aria2 separate from yt-dlp, no default torrent-over-Tor | `spotify.py`, `torrent.py`; `test_spotify.py`, `test_torrent.py` | Preserve existing scope while extending sites; no encrypted Spotify decryption, no false privacy guarantees; regression QA |

## P2: components, application updates and controlled public releases

| ID / status | Acceptance criteria | Related code/tests now | Remaining work / QA |
| --- | --- | --- | --- |
| R01 Partial | Installed/latest/compatibility/check/update/error/rollback separately shown for app, stable/nightly yt-dlp, provider, FFmpeg/probe and Companion | `components.py`, `settings_window.py`, `yt_runtime.py`; component/UI/runtime tests; `docs/COMPONENT_UPDATES.md` | Actual installed Chrome/protocol vs shipped version, provider runtime vs import and media provenance remain distinct; no fake compatibility claims |
| R02 Partial | Automatic reasonable checks/backoff + manual check; compatible integrity-checked activation; active-download snapshots | Component catalog and yt runtime timers; `test_components.py`, `test_yt_runtime.py` | App/provider/media/Companion activation not completed by catalog checks; no blind upstream HEAD pulls; test rate-limit/restart/offline/error states |
| R03 Hosted-tested narrow gates | Apple Silicon app contains native host, Node/provider/Canvas, FFmpeg/probe/aria2; native protocol/media/Mach-O/Cocoa launch tests | `build_macos.sh`, specs, workflow, `scripts/check_packaged_*.py`, package tests; `docs/PACKAGED_*.md` | Preserve current successful narrow native gates; packaging qualification depends on exact run/commit; local licence-gated build prohibited |
| R04 Hosted-tested development archive | Versioned archive preserves bundle/signature and launches after extraction, with manifest/checksums/notes; dev separate from stable | `app_archives.py`, `check_packaged_archive.py`; archive/probe tests; `docs/DEVELOPMENT_ARCHIVES.md` | Diagnostic0242 identifies Canvas compiler object; pre-signing runtime-only fix9a06044 passed strict native round-trip/launch in40991415616. No bypass/re-sign. Stable publication/trust, supported volumes and updater recovery still open |
| R05 Partial; safe checkpoint pushed | Public tokenless newer stable metadata/asset integrity/platform/OS checks; private cancellable staging; previous candidate preserved | `app_updates.py`, `settings_window.py`, stable archive policy; update transport/manager/UI tests; `docs/APP_UPDATES.md`; commit049c44d | Retry/ledger/concurrency/redirect/duplicate-JSON regressions fixed and reviewed; no live qualified stable feed. Stage is not install; full native updater/recovery/publication remain open |
| R06 Partial primitive, updater open | Stop-coordinated replacement, durable crash recovery, previous working installation and rollback; no active-download replacement | `app_installation.py`; installation/replacement tests; `docs/APP_REPLACEMENT.md` | Post-exit orchestration/helper/journal/recovery UI and active-job coordination not connected. User approval/destination unresolved; no install now |
| R07 Open approval gate | Controlled hosted release builds only approved exact qualified commit/version; checksums/notes/source/notices; protected explicit approval before publish | Existing validation workflow is **not** release publication | Application licence, dependency/source-offer compliance, Developer ID/notarisation credentials or truthful unsigned status, stable promotion/release workflow and explicit approval. No tag/release/upload now |
| R08 Open acceptance | New nontechnical user downloads qualified app, discovers tools/auth, data/settings/cookies/history survive update/rollback | Existing app and private runtime/data separation | Fresh-user packaged end-to-end test, install destination/filesystem resolution, rollback failure/crash tests and explicit user account/media QA |

## Measured architecture-debt register

These are inspection evidence, not yet crash root causes. Each remediation must
carry regression tests and before/after measurements rather than a speculative
whole-app rewrite.

| Debt | Evidence on 2026-10-30 | Remediation / proof required |
| --- | --- | --- |
| UI concentration | `ui.py` 2,219 lines; `settings_window.py` 762; queue admission and cleanup worker extracted, orchestration still concentrated | Extract presentation/model/queue service incrementally; preserve behavior/DB compatibility and measure coupling rather than only moving lines |
| Per-row queue objects | `_refresh_queue` uses QTableWidget, per-row QProgressBar and formatted cells; structural clear/rebuild when IDs/columns differ | Benchmark allocation/RSS/native ownership/selection across 100–5,000; use model/delegate/incremental updates where measured |
| Full queue/history work | `_refresh_queue` traverses all jobs; `_refresh_history` allocates every table item | Profile event frequency/CPU/GUI stalls before coalescing dirty IDs and paging/model decisions |
| Per-job persistence: admission/status/removal batched | Atomic iterable transactions; media admission saves before UI publication, large status/removal actions commit32-ID slices | Rollback/phantom/partial cleanup regressions pass. Small actions/restart still per-job; collection/relaunch, fault recovery and GUI enqueue latency remain |
| Modal batch loop: narrow fix verified | Previously one prompt per selected job; now one ID snapshot/one native keep-default dialog,800-job tests pass | Retain broader bounded asynchronous cancellation, per-item failure aggregation, collection controls and realistic worker/file-race qualification |
| Task admission | `TaskManager.start` creates a QThread per admitted task; callers own bounds | Measure actual concurrency/admission/callback queues; scheduler/backpressure tests, no per-queued-job thread explosion |
| Unknown native crash | Real QA reports crash; baseline now measures 15s UI stalls at800 and24s at1,000;5,000 times out.100-item profile assigns0.235/0.252s to cell setText | Native crash still not reproduced/classified. Fix the measured refresh bottleneck with causal tests/after benchmarks; continue isolated native/race reproduction, not a guessed crash explanation |

## Next checkpoints and reporting contract

1. Independently verify/publish the asynchronous owned-file cleanup checkpoint;
   inspect its exact hosted results without cancelling an in-progress run.
2. Continue P0 queue model/view, bounded restart/selection/collection controls,
   persistence recovery and native crash classification from measured evidence.
3. Design system/research/mockups and **approved** professional native screens;
   real visual QA before claiming polish.
4. Real downloaded-media viewer/playback (separate from Inspect Video/preview).
5. Site-scoped auth/privacy/first run and broader source qualification.
6. Finish controlled component/application update, recovery and release gates.

After every checkpoint update this file with actual commits, exact CI evidence,
test/benchmark results, screenshot paths (currently **none for the new redesign**),
verified vs unverified behavior and next priority. Never remove unfinished rows
merely because a nearby feature or test exists. Explicit user live-validation,
licence, destination and release-approval dependencies remain visible.
