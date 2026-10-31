# MediaGrabber feature backlog and qualification ledger

Updated 2026-10-31. This extends, rather than replaces, the Reliable Downloads,
Better UX and Public Releases master goal. The Critical UX, Scalability and
Architecture Addendum changes the implementation order below. An existing helper,
passing unit test or metadata inspector is not evidence of a finished feature.

## Current checkpoint and restrictions

- Development branch: `improvement/download-reliability`. Latest hosted-tested
  checkpoint: `4c3412422d1bfad7fa888b79e78a0c2f26bae9ab`, run `41206020420`,
  all jobs passed. Actual logs: Linux742 (one warning); macOS backend60, Swift25 and protocol9;
  bundled provider/media, Cocoa startup/clean shutdown, replacement backup and
  strict extracted-archive verification/launch passed. Archive141896224bytes,
  SHA256 `fa43d7323c332f83df9e7a23330ebee75acc587f5d60b19aa39ffd2ec560108e`.
  No release asset was uploaded or installed.
- Earlier Canvas failure (`40989481899`, extracted `ImageData.o`) was fixed by
  staging only the required `canvas.node` before normal signing (`9a06044`).
  Strict signature verification was not bypassed. Later green runs include this
  fix, atomic admission (`223737b`), bounded status actions (`d5b3365`) and
  keep-files removal (`90e3d3b`). Detailed evidence remains in QUEUE_SCALE.md.
- Asynchronous owned-file removal checkpoint: **646 Python tests passed
  in22.62s**, JS10/protocol9 matched, pip check clean. FileRemovalService admits
  one owned worker with at most32 copied jobs; GUI owns persistence and counts.
  Stop immediately reports pending work, finishes the admitted slice and stops
  future slices. Partial filesystem/DB failure retains entries; shutdown retains
  uncertainty evidence and still drains workers after a marker-persistence error.
  Entire confirmed removal snapshots supersede earlier pending restarts.
- Synthetic cleanup100/800/1,000/5,000 probes pass with one confirmation, one
  cleanup worker and zero GUI cleanup calls; no actual user files touched.
  The paint follow-up passed the exact hosted run above. Native crash classification,
  real Trash/cross-volume QA, broader memory work, bulk restart and collections
  remain unfinished; no broad crash/scale/release acceptance is implied.
- Queue-only QTableView/immutable presentation model/native proxy/painted progress
  now replace per-row queue items/widgets. In-place changes and incremental row
  operations preserve UUIDs; one progress callback presents/notifies one queue row.
  Full local **664 tests passed24.08s**, JS10/protocol9/pip check clean. Independent
  review ran10 model tests and500 randomized model/proxy transitions; one Important
  first-population sizing defect was reproduced RED and fixed in all3views.
- Paired isolated423160a/current synthetic probes:5,000 peak RSS383.06→278.77MiB,
  enqueue0.885→0.589s;800 peak180.19→158.73MiB. Queue progress widgetsN→0.
  This does not fix history/playlist allocations, leaks or native crashes. Two
  real progress callbacks still take~0.45s at5,000 despite targeted queue updates;
  profile attributes0.530/0.537s to full history refresh (10000decoded jobs,
  70000cell writes). Detailed evidence in QUEUE_SCALE.
- Offscreen synthetic1180x820 light/dark queue renders were captured and inspected.
  Dark theme switching leaves stale light child/table palettes; reproduced also
  on the exported423160a baseline, not claimed introduced/fixed by this model.
  No professional redesign/mockup/native fullscreen acceptance is supplied.
- Render acceptance caught horizontal cells painting vertical progress fill despite
  correct percentage text. Missing Qt State_Horizontal and layout direction now
  have real Fusion pixel geometry tests, LTR/RTL both observed RED→GREEN.
  Full local **666passed22.30s**, JS10/protocol9/pipcheck clean. Updated Light
  render inspected; this narrow follow-up also passed hosted run41169869112.
- Hosted-tested native queue diagnostic: share the real synthetic GUI/SQLite/owned-
  worker exercise between source benchmark and opt-in frozen startup checker.
  Four sizes100/800/1000/5000, two cycles each; source CLI matrix passes. Reports
  require exact persisted counts, two workers, zero final owners, one keep-files
  confirmation/cycle, no per-row widgets and measured RSS/thread/heartbeat/SQL.
  No personal data/network/Keychain/real deletion; native crash traces are bounded
  and redacted. Exactrun41172016114 passes the frozen Cocoa matrix; real transfers,
  restart of the process, leak and user crash classification remain open.
  Review fixes require actual cancellation acknowledgements/zero worker errors,
  independent read-only SQLite visibility plus positive write commits, and retain
  late teardown abort stacks. Full local702passed46.87s, extension10/protocol9
  and pip check clean; no skips. Breadcrumb retention/long-stderr trace scanning
  are deferred diagnostic improvements, not silent qualifications.
- User clarification2026-10-31: the reported large-queue incident left its window
  open but frozen, not an observed quit/crash dialog. Prioritize main-thread stall
  investigation. This is not proof of one cause or absence of every native fault.
- Hosted-tested history hot-path correction, exact4c34124/run41206020420:
  immutable seven-column/order snapshots
  avoid SQL/history-cell rebuilding for progress/bytes/speed/ETA alone. Existing
  SQL filters and explicit metadata/status refresh stay unchanged. History still
  uses QTableWidget; full model migration/other bottlenecks remain. Initial tests
  also exposed two invalid assumptions that Tor Browser's9150/9151 were free;
  synthetic owned-port tests now retain real reservation/exclusion coverage without
  stopping the user's Tor process. No test skips or production Tor changes.
  Review's two Important stale-state findings are fixed with dirty-state/explicit-
  writer invalidation and13RED→GREEN regressions. Full742passed62.14s; focused
  history/bulk75passed8.85s; extension10/protocol9/pipcheck/shellsyntax clean.
  Final paired5,000 steady callbacks0.505451→0.000969s;2history queries/70,000
  cells→0/0, while2writes/2commits remain. Single paired observations, not full
  freeze/live-media/memory acceptance. Native5000probe still measured1.36s max
  operation gap; first unseen-status callback still queries history once.
- In-progress Q04 queue selection: native kind/status/literal-search filters,
  explicit all/filtered/viewport/none/status scopes and truthful counts/details.
  Hidden memory cannot enter actions; None clears it; search/status do not format
  the source list.800/5000filtered keep-file removal targets/one prompt tested.
  Compact/standard real offscreen renders inspected; no P1 redesign acceptance.
  Existing frozen matrix now requires actual selection-control evidence, not just
  source tests. Full788passed57.77s, JS10/protocol9/pipcheckclean; independent
  review found no Critical/Important. Exact new hosted qualification pending.
  Deferred minor: open details-dialog caption can name the old selection or say
  removed when merely filtered out; body/action IDs remain correct. All rows kept.
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
| Q01 Release blocker; user describes freeze | Synthetic 100/800/1,000/5,000-item analysis/enqueue/start/pause/cancel/remove/reload runs; classify UI stall/exception/native fault/OOM/unbounded work from evidence | `scripts/benchmark_queue.py`, `queue_check.py`, model/scale/bulk/history tests, `docs/QUEUE_SCALE.md` | Header/queue model fixes and native two-cycle matrix pass. User reports an open frozen window; no observed process crash. Remaining history/playlist stalls, memory growth, long-run/live QA; do not claim a unique cause or leak freedom |
| Q02 Portable-tested fix | Removing 800 selected jobs opens at most one confirmation, shows actual total and running/completed counts; Cancel changes nothing | `ui.py:remove_selected`, `_confirm_remove`; `test_queue_bulk.py` | One selected-ID snapshot/one native dialog, keep-files default, latest post-modal inventory and deferred active-removal tests now pass; native visual/realactive QA remains |
| Q03 Partial; bounded worker connected | Default keeps files; optional deletion touches only verified job-owned paths; no wildcard destination deletion | `file_ownership.py`, `file_removal.py`, `ui.py`; ownership/service/bulk tests | One explicit decision;32 snapshots/one owned worker after transfer owners stop; successful cleanup precedes atomic DB removal. Temp-owned/foreign, stop/admission/DB/close failures tested; real Trash, cross-volume and realistic transfer races remain |
| Q04 Portable-tested/reviewed; hosted pending | Select all/none/visible/filtered; select waiting/running/completed/failed/paused/cancelled jobs | `queue_selection.py`, raw model roles, native controls; selection/model/UI/packaged-gate tests; QUEUE_SELECTION.md | Source scopes/counts/hidden-memory/live UUID/action tests and full788 pass; independent review no Critical/Important. Exact frozen hosted gate remains. Not analysed-playlist checkbox selection |
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
| U02 Open; diagnostic renders only | Real compact/standard/large/fullscreen screenshots in light/dark show readable, aligned unclipped UI; retain icon/native PySide6 | workspace queue-model current/baseline light/dark PNGs; UI/model tests | Offscreen1180x820 diagnostic is not Cocoa/fullscreen/design acceptance. Existing dark switch stale-child palette reproduced against baseline; fix with rendered regression. Title/destination remain narrow; approved design/resize QA still required |
| U03 Partial | Large analysed playlist has resizable remembered panels, collapsible options/preview, search, visible/all/none/invert, counts, keyboard/multi-selection | `ui.py`, `settings.py`; `test_playlist_workspace.py`; `docs/PLAYLIST_WORKSPACE.md` | 800–5,000 scale qualification and visual QA; current playlist table is still item-based |
| U04 Partial | Lazy playlist thumbnails and real duration reflect current selected video, avoid N requests and route fallback | `thumbnail_cache.py`, `ui.py`; `test_thumbnail_cache.py`, `test_playlist_workspace.py` | Distinct from viewer: real rendered thumbnail/duration QA, scrolling/large-list responsiveness, missing/slow/cancelled responses |
| U05 Partial | On-demand per-video format/audio/language and manual/automatic subtitle metadata; only available controls; safe overrides | `media_details.py`, `media_details_dialog.py`, `formats.py`, `subtitle_mux.py`; media-details/formats/subtitle tests | Real authorised media and batch language/subtitle outputs with explicit user participation; no invented Original/default identity or 800 automatic inspections |
| V01 Open | Discoverable downloaded-media grid/list with thumbnails/metadata, search/filter/sort/browsing history and Finder open/reveal | History currently offers Open/Reveal; `ui.py:_history_context_menu` | Build actual library/viewer; Inspect Video is metadata, **not playback**; add index/model and missing-file tests |
| V02 Open | Actual video/audio playback, play/pause/seek/volume/fullscreen, duration/timeline, available audio/subtitle choice | No qualified in-app playback implementation | Evaluate QMediaPlayer/QVideoWidget, packaged backend/codecs and safe external-player fallback; explicit user validation on real local media and packaged app; unsupported errors truthful |
| A01 Partial/incremental | Separate presentation/models, queue/batch service, execution/scheduling, auth/session, inspection/playback, persistence, updates and diagnostics with clear ownership | New `queue_model.py`, `display_format.py`, `queue_batch.py`, `file_removal.py`; existing backend helpers | GUI-owned model and bounded services separated, backend/DB unchanged. Continue debt register, typed/testable interfaces and measured remediation; no whole-project rewrite |

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
| UI concentration | `ui.py` 2,169 lines; settings762; queue presentation/formatting/model plus batch/cleanup responsibilities extracted, orchestration still concentrated | Preserve behavior/DB compatibility; measure coupling, not only moved lines |
| Per-row queue objects: removed | QTableView/model/native proxy and style-painted progress; no per-row Qt item/widget ownership; incremental append/remove, rare reset with UUID restoration | Paired100–5,000 RSS/widget/latency evidence in QUEUE_SCALE. History/analysed playlist still item-based; no global memory/leak guarantee |
| Full queue/history work: partial | Targeted queue progress; full history consumed0.530/0.537s in two callbacks/10000decoded jobs/70000cells. History projection guard in progress | Verify zero unchanged-history queries/cell replacements with immutable/filter/failure regressions and paired metrics. Metadata refresh/model migration still open |
| Selection/details minor | Review: remove primaryA from selectedA+B; B stays correctly actionable but inline details become blank | Reconcile surviving details target in next selection/UX checkpoint; not an action-ID mix-up |
| Existing theme switch rendering | Light→Dark leaves light/stale child/table palettes in both baseline423160a and model renders despite correct app palette | Rendered regression and Qt repolish/inheritance diagnosis; do not claim polish from app-palette assertions alone |
| Per-job persistence: admission/status/removal batched | Atomic iterable transactions; media admission saves before UI publication, large status/removal actions commit32-ID slices | Rollback/phantom/partial cleanup regressions pass. Small actions/restart still per-job; collection/relaunch, fault recovery and GUI enqueue latency remain |
| Modal batch loop: narrow fix verified | Previously one prompt per selected job; now one ID snapshot/one native keep-default dialog,800-job tests pass | Retain broader bounded asynchronous cancellation, per-item failure aggregation, collection controls and realistic worker/file-race qualification |
| Task admission | `TaskManager.start` creates a QThread per admitted task; callers own bounds | Measure actual concurrency/admission/callback queues; scheduler/backpressure tests, no per-queued-job thread explosion |
| Reported UI freeze; other faults unproven | User clarifies window stayed open. Initial baseline measured15s stalls at800/24s at1000; header/model fixes now pass frozen two-cycle matrix | Further remove measured history/playlist GUI work, profile retention/long gaps and reproduce live conditions only with explicit user participation; no invented native-crash cause |

## Next checkpoints and reporting contract

1. Finish/qualify native queue filtering/selection after the successful history
   hot-path checkpoint; preserve exact hosted evidence and full backlog.
2. Continue P0 history/progress coalescing, bounded restart/selection/collection controls,
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
