# Migration phases — proposed plan for review

These phases describe future work. Only the baseline test correction, design
documents and CI structure are included in this task. No phase authorizes Swift
features or backend extraction without review. Keep the Python app available at
every checkpoint; do not run both frontends against the same writable state.

## Phase 0 — Baseline and reproducible evidence

- Scope: verify baseline SHA/submodule, trusted OS-native media tools and Python
  suite; correct machine-dependent tests without weakening behavior.
- Success: auth/settings 19 passed; full suite 222 passed in Linux Cloud. Record
  dependency versions and unavailable native/live checks. Current phase complete.
- Tests: entire Python suite, pip check and test diff review.
- Rollback: original commit plus separate test correction; no application change.
- Python reference: all source/tests; absent Chrome profile means empty/None.
- macOS CI: not required for Linux baseline; required before claiming native QA.

## Phase 1 — Extract and qualify the backend contract

- Scope: implement protocol DTOs/fixtures and non-Qt service ownership around
  existing analysis/download/database/runtime modules. Qt uses an adapter to the
  same service. Extract scheduler/state responsibilities from ui.py, not engines.
- Success: equivalent Qt behavior; IPC snapshot, cancellation, revision/attempt
  fencing, paging, reconnect and durable ownership proven; no widget imports in
  headless worker. Protocol command subset advertised honestly in capabilities.
- Tests: existing 222 baseline tests plus headless contract/error/secret/crash/
  concurrency tests, independent comparison fixtures rather than self-serialization
  alone. Add JSON fixtures to shared/protocol/v1/ with provenance.
- Rollback: run original Qt entry point and preserve legacy schema/state backup.
- Python reference: ui.py dispatcher/action methods, tasks.py, database.py, models.py,
  downloader.py; preserve strong task ownership/cooperative shutdown.
- macOS CI: required for process launch/provider imports on macOS; Linux covers
  deterministic headless protocol tests.

## Phase 2 — Minimal native shell and state client

- Scope: separately approved swift/ package with Foundation Domain/BackendClient
  and SwiftUI shell. Read-only queue snapshot first; native fixture service for
  tests. No download feature needed to qualify the boundary.
- Success: hello/version negotiation, pipe decoding, MainActor state, unavailable
  worker display and clean shutdown; macOS 12 deployment compatibility.
- Tests: Swift unit tests against shared fixtures and hosted shell launch smoke;
  malformed frames, stale events, worker crash, no auto-replay.
- Rollback: close native worker and reopen Python app, state unchanged.
- Python reference: app.py lifecycle, tasks.py ownership and Database load recovery.
- macOS CI: required; `swift build` and `swift test` must run with nonzero tests.

## Phase 3 — Analysis and preview

- Scope: inputs, classification, searches/Watch Later/playlists, candidate table,
  thumbnails and select/all/none/invert; explicit Spotify selection.
- Success: same safe items/order/collection metadata/effective auth, cancellable
  analysis and ID-bound selection; no unsigned headers reach native logs.
- Tests: parsing/auth/Spotify/thumbnail Python fixtures plus Swift event/selection
  tests and UI cancellation smoke; no private user cookies.
- Rollback: Python Analyse remains the functional reference and fallback.
- Python reference: parsing.py, auth.py, downloader.analyse_with_authentication,
  ui._analysis_ready/enqueue_selected, spotify.py, thumbnail_cache.py.
- macOS CI: required for UI/preview integration; Linux for backend fixtures.

## Phase 4 — Durable queue foundation, history and recovery

- Scope: native view/actions backed by one Python database writer; stable UUIDs,
  history search, warning details, exact inventories and action grants. Prepare
  scheduling before allowing native downloads.
- Success: selection survives refresh, old payloads read without destructive
  migration, reconnect yields Interrupted, file actions cannot affect unrelated
  paths; explicit replace/list-only/Trash choices.
- Tests: legacy database fixtures, crash between commit/event, lock contention,
  removal/restart races, symlink confinement and native open/reveal tests.
- Rollback: restore tested backup only while both frontends are closed; use Qt.
- Python reference: models.py, database.py, file_ownership.py, ui.py queue/actions.
- macOS CI: required for Finder/Trash integration; Linux for persistence/races.

## Phase 5 — Download, progress, retry and output verification

- Scope: selected jobs dispatch with immutable options/runtime snapshots; typed
  hooks, progress/stages/warnings and bounded retry/metadata refresh; pause/cancel/
  resume/retry/restart.
- Success: no completion until required media verification succeeds; optional
  sidecar failures retain usable output and warnings. No stale progress overturns
  stop intent. UI never infers transfer from a live extractor.
- Tests: downloader/format/watchdog/progress/ownership parity, local HTTP fixture
  transfers, shutdown mid-job, restart confirmation, output verification.
- Rollback: drain/interrupt owned worker, open same compatible state in Qt.
- Python reference: downloader.py, formats.py, compatibility.py and existing tests.
- macOS CI: required for native-engine integration; Linux backend regression suite.

## Phase 6 — Settings, auth, routing, provider, runtime and Tor

- Scope: complete typed settings editor, Keychain platform service, cookie-path
  selection and auth reporting, routing snapshots, provider readiness, runtime
  controls and separate Tor layer states.
- Success: Apply/Cancel parity, credentials never persisted/logged, private errors
  never remove auth; output accurately states each operation's tested route.
  Resolve login-test routing and provider readiness separately. Tor retry policy
  review completed before enabling any automatic circuit action.
- Tests: settings/auth/network/runtime/provider fixtures, owned Tor control tests,
  native Keychain tests with ephemeral CI test items removed after the run.
- Rollback: Qt settings remain readable, worker stopped, secrets stay in Keychain.
- Python reference: settings_window.py, settings.py, auth.py, provider.py,
  network.py, managed_tor.py and yt_runtime.py.
- macOS CI: required; private live account tests are opt-in manual QA, never CI.

## Phase 7 — Converter, subtitles, metadata and torrent UI

- Scope: expose existing engine plans and file selections, not replacement engines.
  First fix/qualify converter cancellation/stderr draining/overwrite permission
  and quiet-torrent cancellation in independent backend changes.
- Success: verified atomic outputs; optional subtitle failure retention; responsive
  cancellation; private torrent discovery safeguards; Direct/System-only peers.
- Tests: all current real-media converter/subtitle/artwork/chapter fixtures,
  planned child-process cancellation tests, torrent metadata/argv/event fixtures.
- Rollback: Python converter/torrent interface retained; no extra file deletion.
- Python reference: local_converter.py, subtitle_mux.py, media_verification.py,
  torrent.py, ui.py converter options/actions.
- macOS CI: required for media encoders and native selection UI; no live swarm.

## Phase 8 — Parity and native quality gate

- Scope: resolve every Preserve checklist item and record decisions for each
  Review/Defect item; accessibility, lifecycle stress, performance and privacy.
- Success: same sanitized fixture outcomes, no missing required statuses/warnings,
  no unintended persistence/log fields; documented macOS playback/manual UI QA.
- Tests: Python suite, Swift unit/integration/UI tests, cancellation/crash stress,
  controlled media QA on hosted macOS and authorized user machine without compiling.
- Rollback: release candidate remains opt-in; Python app still supported.
- Python reference: entire suite plus explicitly reviewed behaviors, not bugs.
- macOS CI: required; results separated from manual private/live access evidence.

## Phase 9 — Packaging and distribution qualification

- Scope: trusted pinned worker/tool artifacts and license manifests; remove Qt
  from worker package only after import tests prove independence; separate arm64
  and x86_64 builds. Review dynamic updates, sandbox and hardened runtime.
  Signing/notarisation added only in separately authorized release workflow.
- Success: unsigned smoke first, then authorized signed builds; native app/worker
  launch without system Python or Homebrew; packaged fallback/provider/engines
  work; correct deployment target; no global writable locations required.
- Tests: bundle architecture/load/launch checks, converter fixtures against bundled
  engines, runtime rollback, Gatekeeper/notarisation where credentials authorized.
- Rollback: retain prior Python release and documented state downgrade/backup route.
- Python reference: build_macos.sh, PyInstaller spec, tool provenance and runtime tests.
- macOS CI: required; owner's local Xcode/sudo/licence acceptance never required.

## Recommended next task and outstanding decisions

Review architecture/protocol/phase documents first. Then authorize Phase 1 only:
write an executable extraction plan and protocol fixtures, retaining Qt behavior.
Do not start the complete Swift port. Qualify runner/toolchain/deployment target,
distribution/update policy and secret delivery before native release work.
CI hosted executions and live/private/native checks remain unrun in this task.
