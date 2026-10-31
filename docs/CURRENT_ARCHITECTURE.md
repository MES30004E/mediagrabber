# Current architecture — Python/PySide6

This source map describes the Stage 1 Python baseline, not a proposed rewrite.
See `ARCHITECTURE.md` for the longer runtime/lifecycle narrative and
`CODEX_CONTEXT.md` for test prerequisites and development restrictions.

## Entry and UI

`launcher.py`, package `__main__.py`, and the console entry point call
`app.main()`. It configures logging, initialises `YtDlpRuntimeManager`, then
constructs QApplication and `ui.MainWindow`. The framework is PySide6 Qt Widgets.

`ui.py` owns Download/Queue/History/Console/Settings, menus, preview selection,
dispatch, and local conversion presentation. `settings_window.SettingsWindow`
edits a working copy through General/Downloads/Network/Authentication/Torrents/
Advanced pages, with Apply/OK persistence and Cancel discard.

## Analysis and downloads

```text
input → parsing.input_kind → ui._analysis_operation
  → downloader.analyse_with_authentication → analyse_target → MediaItem[]
  → preview selection / automatic enqueue → _enqueue_payload → _dispatch
  → download_job (media) / download_torrent (torrent)
```

`parsing.py` splits lines and distinguishes HTTP(S), search, Spotify, YouTube
Music, torrent files, magnets, and explicit Watch Later targets. The exact
`:ytwatchlater` keyword is preserved. Watch Later playlist/feed aliases use
canonical `https://www.youtube.com/playlist?list=WL`. Other playlists and watch
URLs retain their input, and ordinary text becomes `ytsearchN:...`.

`analyse_target` calls the yt-dlp Python API with `extract_flat="in_playlist"`,
proxy, provider args, and authentication options. Collection entries become
individual MediaItems; empty entries are skipped. Analysis has no separate
unauthenticated Watch Later shortcut. `download_input` may analyse/enqueue
without a preview; multiple lines start independent analysis tasks.

`download_job` extracts current metadata, inspects playable formats, selects
concrete IDs through `formats.resolve_available_format`, and processes the
result. It uses progress/postprocessor/final-file hooks, not parsed terminal
progress. Transfer/fragment retries are bounded; a transfer HTTP 403 triggers
one fresh metadata extraction. Diagnostics distinguish analysis, resolution,
transfer, optional processing, and verification. Optional processing can result
in Completed with warnings rather than destruction of usable media.

## Authentication/provider/network

`auth.authentication_options` uses yt-dlp's cookiesfrombrowser or cookiefile.
Auto starts without cookies and retries selected browser authentication on
recognised account-required errors. Explicit authenticated modes can retry once
without cookies for public format failures, never for recognised private/account
errors. Download uses the same policy, with effective mode persisted. This is
message-based policy, not verified entitlement inference. No cache scraping.

`provider.py` discovers external HTTP `/ping` or script homes/JS runtimes and
supplies yt-dlp extractor arguments. The pinned bgutil plugin retains its own
HTTP-first/proxy-forwarding behaviour. It is included by import-path discovery
and PyInstaller source bundling, not rewritten or automatically started.

`network.ProxyConfig` yields explicit proxy URLs; custom SOCKS and Tor use
socks5h for remote DNS. Direct/System-Proton yield no explicit proxy and rely
on system routing, not application-controlled VPN connection/verification.
`managed_tor.ManagedTor` launches only the Tor executable with app-owned data,
dynamic loopback SOCKS/control ports, cookie authentication, ownership checks,
and bootstrap state. External Tor discovers conventional endpoints without
owning its process. Existing Managed Tor control/target retry logic is bounded
but requires a future policy review; no automatic escalation beyond it is approved.

Tor Browser defaults to current-user Applications if present, else system
Applications. User-saved paths are preserved. Settings authentication testing
currently applies a proxy only to Managed Tor; normal download routing is separate.

## Jobs, lifecycle, and persistence

`models.py`: MediaItem, DownloadOptions, DownloadJob, JobStatus. Jobs have stable
IDs, options, progress, warnings, diagnostics, Tor/torrent fields, and exact file
inventories. `DownloadJob.to_dict` excludes preview request headers from history.

`database.Database` stores indexed job fields plus JSON snapshots in SQLite WAL.
History queries the same jobs, not a second independent history store. Active
persisted states reload as Interrupted rather than silently resuming.

`tasks.TaskManager` strongly owns TaskThreads and cancellation events until
thread completion. Signals/callbacks are delivered on the GUI thread; settings/
job snapshots are copied across boundaries. Shutdown asks workers to stop and
waits, without forced QThread termination. Cancellation is cooperative and not
implemented by every external processing operation.

Resume/Retry keep resumable state. Restart waits for worker ownership to end,
then deletes only recorded state and resets progress. `file_ownership.py` protects
unrelated files/directories and uses Trash for completed outputs where practical.
Queue selection is tied to job ID rather than changing row indices.

Large status/retry and keep-files removal use `queue_batch.QueueBatch`:32-ID
GUI timer slices, one active batch, atomic DB transactions, explicit waiting-ID
settlement and dispatch coordination. Optional file removal uses
`file_removal.FileRemovalService`: one TaskManager-owned thread, at most32 copied
job inventories, existing safe ownership/Trash helper, and no worker-side Qt or
database mutation. Each slice waits for its transfer owners and cleanup thread
to stop before the next slice. Successful cleanup precedes atomic entry deletion;
partial cleanup or DB failure retains entries with a warning. Stop finishes the
admitted slice while preventing future slices. Shutdown suppresses late results,
persists uncertainty where possible, and preserves the running marker if that
persistence fails; a marker failure cannot skip owned-worker shutdown.

Queue presentation now uses `queue_model.QueueTableModel` with immutable display
rows, stable UUID roles, a native QSortFilterProxyModel and style-painted progress
in QTableView. No queue QTableWidgetItems or per-row progress widgets are created.
Append/remove use begin/end row notifications; rare reorder/column changes reset
and restore selection by UUID. Hidden-view selection memory cannot enter actions
unless visibly selected. Single-job progress updates only its presentation row;
full refresh still synchronizes all snapshots. Model mutations require its GUI
thread. `display_format.py` shares existing byte/duration presentation helpers.

`queue_selection.QueueFilterProxyModel` combines kind, raw-status categories and
literal normalized search over immutable STATUS_ROLE/SEARCH_ROLE. Search/status
changes refilter without rebuilding source presentation. Its native selection
helpers group ranges, map UUIDs and distinguish viewport rows from all filtered
results. The UI owns remembered IDs/counts and reconciles visible details after
filter/reset/live membership changes; hidden memory never supplies action targets.
Explicit replacement/None clears hidden memory. No queue execution, database,
authentication or networking is performed by these controls. See QUEUE_SELECTION.

These are incremental prerequisites, not completed scale/crash qualification.
History/analysed playlists still use item tables, full history refresh is
expensive, and bulk restart/collection/dedup work is incomplete. See
`docs/QUEUE_SCALE.md` and `docs/FEATURE_BACKLOG.md` for measured limits and QA.

`queue_check.exercise_queue` is an explicit disposable-state diagnostic, never a
normal startup or transfer path. The source benchmark and startup diagnostic
share real GUI/SQLite/TaskManager operations but replace transfers with two
cancellation-only workers, guard external I/O and drain owners before restoring
guards. `--startup-check REPORT --queue-items {100,800,1000,5000}` runs two cycles
after window exposure. The packaged verifier requires complete frozen/Cocoa
cycle and measurement evidence; failures retain bounded redacted native stacks.
Workers must actually acknowledge their cancellation events without errors;
read-only independent SQLite payload comparison verifies committed cancellation
and removal, not merely the writer's own uncommitted view.
This tests synthetic queue behavior, not accounts, real downloads, leaks or a
whole-process restart. Normal startup and downloader/auth architecture are unchanged.

`history_presentation.py` owns immutable seven-column/order snapshots, not widgets
or I/O. Progress callbacks still save the full job and update queue/details, but
only refresh history when its presentation/order/filter fields differ. Full
history queries/rendering remember DB-derived snapshots after successful render;
one explicitly persisted callback row is remembered even when filtered out.
Unrelated mutable/unpersisted jobs are never acknowledged en masse. Existing SQL
LIKE/status/order, explicit refresh and context-menu job-ID behavior are retained.
There is no delayed timer, new worker, database schema or auth/network change.
Every explicit full history refresh starts dirty and only successful rendering
clears that flag. Successful non-callback writes invalidate history too; small
status actions/watchdog/restart/stop-seeding refresh once, while existing batch/
removal completion owns its full render. Dispatch invalidates for the next
callback, rather than rebuilding per unchanged callback. Closing-only persistence
does not render a disappearing window. Failed queue rendering after a committed
change cannot hide the pending history refresh.

`settings.SettingsStore` atomically writes schema-6 mode-0600 settings, migrates
legacy preferences, and recovers corrupt JSON. `keychain.py` calls macOS security
for proxy passwords; passwords are not serialized as preference fields.

## Processing and runtime tools

- `formats.py`: format constraints, audio conversion, yt-dlp postprocessors.
- `compatibility.py`: source-aware QuickTime/universal MP4 conversion/remux.
- `local_converter.py`: immutable ConversionOptions/ConversionPlan, five profiles,
  container/codec checks, selective transcoding, temporary output, verification,
  atomic publish. It is separate from download compatibility processing.
- `subtitle_mux.py`: optional sidecar acquisition/mux and language/codec verification.
- `media_verification.py`: ffprobe JSON, stream/container/chapter checks and Mutagen artwork checks.
- `thumbnail_cache.py`: allowlisted preview headers, bounded cache, proxy-aware fetch.
- `console.py`, `logging_setup.py`, `job_diagnostics.py`: bounded/redacted Console,
  rotating local logs, classified persistent errors/warnings and safe format summaries.
- `organisation.py`: collection folders, names, and duplicate-root prevention.
- `yt_runtime.YtDlpRuntimeManager`: stable official release checksums, structural/
  provider validation, atomic activation, version cleanup, rollback, bundled fallback.
  Dispatch captures a RuntimeSnapshot so activation affects future jobs.
- `paths.py`: bundled/project/PATH binary discovery and user-local state locations.
- `diagnostics.py`: component availability and output permission checks.

Runtime yt-dlp update traffic uses its own HTTPS fetcher rather than necessarily
the selected media proxy. Provider health checks and GUI probes likewise have
their own routing paths; do not describe all app network activity as Tor-routed.

## Torrents and Spotify

`torrent.py` parses bencode/file metadata, fetches magnet metadata through aria2,
and launches separate aria2 subprocesses. **The current implementation parses
aria2 console progress; it is not JSON-RPC.** It supports selection, speeds,
connected peers/seeders, seeding, tracker options, and private-torrent discovery
restrictions. Only Direct/System-Proton are permitted; yt-dlp proxies/Tor are
not forwarded to BitTorrent.

`spotify.py` uses public oEmbed metadata and text/duration candidate scores;
`analyse_target` searches YouTube. No Spotify stream decryption or authenticated
playlist-track expansion exists. Preview selection is implemented; one-click
candidate-enqueue behaviour remains a known limitation.

## Packaging and verification boundary

PyInstaller's spec bundles launcher, source, icons, available media tools, and
provider plugin sources. `build_macos.sh` installs private dependencies, obtains
ffmpeg/ffprobe, tests, packages, and ad-hoc signs. Aria2 acquisition is separate.
Base Python is durable user-local storage, not a temporary directory; exFAT venvs
use copied executables. Build/dist/binaries are not source-control artifacts.

Stage 1 tests passed locally with existing native tools. No fresh packaged build,
live private content, Tor traffic, or torrent swarm result is claimed. Preserve
these distinctions when reporting parity or Cloud readiness.
