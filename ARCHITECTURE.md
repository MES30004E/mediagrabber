# Architecture

This describes the existing Python/PySide6 application. [docs/CURRENT_ARCHITECTURE.md](docs/CURRENT_ARCHITECTURE.md) provides the Stage 1 source map and limitations; [docs/CODEX_CONTEXT.md](docs/CODEX_CONTEXT.md) is the future Cloud handover. No Swift implementation, backend IPC, or Swift CI exists in this baseline.

```text
PySide6 UI
  ├─ analyser worker ── yt-dlp Python API ── extract_info(download=False)
  │                         └─ Spotify oEmbed → ytsearch candidates
  ├─ queue dispatcher ─ yt-dlp Python API ── progress/postprocessor hooks
  ├─ SQLite database ── durable jobs and history
  ├─ JSON preferences ─ download/network/UI defaults
  └─ diagnostics
       ├─ ffmpeg / ffprobe
       ├─ Tor SOCKS5H endpoints
       └─ bgutil HTTP /ping → external script fallback
  ├─ ManagedTor ── owned Tor subprocess → isolated data directory → SOCKS5H
  └─ torrent worker ── aria2c subprocess → independent Direct/System network path
```

The GUI thread is the only thread that updates widgets. Every background operation is owned by one central `TaskManager`; the callable runs directly in a `TaskThread` subclass, so there is no Python-backed worker `QObject` to destroy in a stopped worker thread. A task record holds the task ID, kind, cancellation event, state, callbacks, and strong thread reference until `QThread.finished` reaches the GUI thread. Results, Console events, and progress cross the boundary only through queued Qt signals; callbacks to bound `QObject` methods are weakly held so a task cannot keep a closed window alive. On close, the manager stops accepting callbacks, requests cooperative cancellation, and waits for every owned thread before the UI and database are destroyed. It never force-terminates a Qt thread.

The previous pooled-runnable design did not provide that ownership boundary: transient Python references and Qt's auto-deletion of `QRunnable` wrappers could overlap queued callbacks and window teardown. That matched the captured `QRunnableWrapper` destruction and Shiboken `QObjectWrapper::event`/`cppPointer` crash stacks. The explicit task lifecycle removes the unsafe wrapper lifetime and cross-thread callback path.

Each active download has its own cancellation event and immutable job/settings snapshots. Pause stops that job's worker while retaining yt-dlp `.part` files; resume creates a new task and lets yt-dlp continue the partial download. Media, torrent, analysis, Tor-wait, provider, diagnostics, connection-probe, and updater tasks have independent state and concurrency limits.

## yt-dlp runtime updates

The signed app always contains a bundled yt-dlp fallback. At startup the runtime manager selects a previously verified user runtime from `~/Library/Application Support/Morgan Media Downloader/runtime/yt-dlp/`, then the visible GUI schedules an official stable-release check through the task manager. Downloads receive an immutable runtime snapshot when dispatched, so activation changes only future jobs. Update artifacts are downloaded to a partial file, checked against the official `SHA2-256SUMS`, structurally inspected and imported, tested for bgutil plugin discovery, moved into a versioned directory, and activated through atomically replaced metadata. Current, previous, and one additional version may be retained; failure restores the previous compatible runtime or the bundled copy.

`DownloadJob` is the persistence boundary. It contains source metadata, immutable download options, status, structured progress fields, output path, and error details. SQLite stores a JSON snapshot plus indexed status/title fields, allowing forward-compatible migration without coupling UI tables to the schema.

Queue selection is persisted by `DownloadJob.id`, not by row or transient model index. Progress-only refreshes update existing table cells and progress widgets in place; structural reloads restore the matching row, scroll position, focus, inline details, and the optional persistent details dialog.

For compatible-output profiles, format preference happens before transfer. The post-download compatibility stage probes actual streams, copies H.264/HEVC and AAC streams when safe, converts only incompatible video/audio/subtitle/artwork streams, writes MP4 fast-start metadata, and probes the atomic temporary result before replacement. Subtitle muxing retains playable streams and QuickTime chapter tracks while excluding opaque data tracks.

The separate local converter builds an immutable `ConversionOptions` specification and a source-aware `ConversionPlan`. The plan resolves Auto codecs, validates container capabilities and Copy requests, decides stream-level copy/transcode/subtitle/artwork actions, and generates an argument-array-only ffmpeg invocation. Outputs are written to same-container sibling temporary files; ffprobe checks the requested extension/container, codecs, tags, stream structure, duration, subtitles, metadata, chapters, and artwork before an atomic publish. This engine does not change the download post-processing contract.

Managed Tor owns its process, isolated data directory, dynamically allocated loopback SOCKS port, dynamically allocated loopback ControlPort, and control cookie. Port selection reserves two OS-assigned endpoints until immediately before launch, excludes 9050/9051/9150/9151, and retries classified bind collisions at most three times. Session state records Morgan's owner PID, Tor PID, endpoints, data directory, launch time, and bootstrap state; stale recovery verifies the command and ownership before terminating anything and refuses active or foreign locks/processes. Circuit rotation authenticates over the runtime ControlPort with the binary cookie and sends `SIGNAL NEWNYM`; it never controls Tor Browser. Exit-specific denial retries rebuild the yt-dlp instance and extraction result from the original URL, with a hard three-rotation ceiling. Process/bootstrap/SOCKS/Internet/exit/target states are recorded independently.

Download activity records extractor, transfer, and post-processing flags plus progress, byte, and transition timestamps. The UI never marks a media job Downloading before resolution selects playable media. A stage-aware watchdog repairs legacy or impossible zero-byte states without timing out a legitimate active extractor or transfer.

Each job also persists exact final, partial, temporary, subtitle, and thumbnail paths plus an optional app-created directory. Restart and removal operate only on this inventory. Resume and Retry preserve it; Restart deletes resumable state and resets transfer metrics only after worker ownership has ended. A collection directory is removed only when every contained path is recorded as job-owned.

YouTube authentication is an attempt policy rather than a global cookie switch. Auto tries public extraction without cookies and retries with yt-dlp's selected browser profile only for explicit login/account errors. Explicit authenticated modes may retry once without cookies only for a format-unavailable error that is not marked private/member/account-required. Downloads inspect the returned `formats` collection and select concrete compatible IDs before processing.

`parsing._watch_later_target` preserves the exact `:ytwatchlater` extractor keyword and normalises explicit Watch Later playlist/feed routes to `https://www.youtube.com/playlist?list=WL`. Host matching is exact; unrelated URLs, ordinary playlists, watch URLs containing playlist context, and free text retain their previous handling. Analysis still uses `analyse_with_authentication`; per-item download still uses `download_job`. Stage 1 does not introduce a separate unauthenticated Watch Later path or change cookie fallback rules.

Metadata, artwork, conversion, and merge stages remain explicit yt-dlp postprocessors. Subtitle handling is intentionally outside the primary transfer: media is completed first, selected sidecars are acquired in an optional pass, ffmpeg muxes them into a same-directory temporary sibling using container-specific codecs, ffprobe verifies stream count/codecs/languages, and only then does an atomic replacement occur. The original media remains untouched on any subtitle failure. The final path is captured through the post hook and inspected with bundled ffprobe; Mutagen metadata is used as the equivalent artwork check for MP4/M4A cover atoms that ffprobe does not always expose as streams.

`job_diagnostics.py` separates metadata extraction, playable-format resolution, transfer, optional processing, and verification. Persisted format summaries contain only ID, extension, resolution, codecs, and protocol—never direct or signed URLs. The live `ConsoleStore` is bounded to 10,000 redacted events and is updated only on the GUI thread after `TaskManager` queued delivery.

The networking layer returns only explicit proxy URLs. Direct and system/Proton modes return no proxy, while custom SOCKS and Tor always return `socks5h://`. Provider configuration is expressed as yt-dlp extractor arguments, allowing the upstream provider's own HTTP-first preference and proxy-forwarding behavior to remain intact.

`settings.json` is the only preferences store. Settings are written to a mode-0600 temporary file, flushed and fsynced, then atomically replaced. The Settings window edits a deep copy so Cancel cannot mutate live state; Apply and OK save through the same callback.

Torrent jobs share the persisted queue model but dispatch to aria2c rather than yt-dlp. Discovery prefers the app-bundled engine, then a user-selected executable, then a user-local PATH executable. Magnet analysis first runs aria2 in metadata-only mode, then populates the normal file-selection table. No yt-dlp proxy is forwarded to aria2, and both validation and the torrent Settings page permit only Direct and System / Proton VPN.
