# MediaGrabber product specification

Updated 2026-11-07 from the Full Product Completion Mission. The authoritative
feature/status/evidence ledger is [FEATURE_BACKLOG.md](FEATURE_BACKLOG.md);
this document defines product acceptance, not a second status ledger.

## Product and workflow

Native Python/PySide6 macOS downloader: simple by default, advanced when needed.
Combine ClipGrab's approachable input flow with Stacher's discoverable capabilities,
without copying proprietary code/artwork. Preserve the original repository icon.

Paste/drop one or more URLs or a search → analyse → preview/select → choose
available quality/audio/subtitles/destination → download → manage and play files.
Ordinary packaged-app use must not require Terminal, Python, Homebrew or Git.
Advanced diagnostics remain available but do not dominate ordinary navigation.

## Acceptance by workflow

- **Input/selection (U03–U05, M01):** genuine titles/duration/thumbnails and only
  available formats/languages/manual or automatic subtitles. Lazy inspection,
  safe cancellation, global defaults plus per-item overrides, responsive lists.
  Preserve filename templates, cover artwork, chapters/metadata, compatibility
  profiles and local conversion. No invented size/language or DRM capability.
- **Queue (Q01–Q11):** stable UUID/collection identity; search/sort and explicit
  selection scopes; bounded asynchronous actions; one confirmation, Keep files
  default. Explicit deletion only of verified owned paths. Resume differs from
  Restart. Dedup/archive and queued edits must survive relaunch and failures.
  Repeated restart must not grow nested attempts or endanger retained outputs.
- **Library (V01–V02):** browse/filter/sort local files, metadata/thumbnails and
  missing-file states; actual audio/video playback, seek, volume, fullscreen,
  supported tracks/subtitles and truthful external-player fallback. Inspect Video
  metadata and playlist preview do not constitute playback acceptance.
- **Accounts/network (D01–D03, AU01–AU02, M02–M05, F01):** truthful prerequisite,
  consent, capture, storage, session and downloader-readiness states; no account
  identity guesses. Session-only/Keychain/anonymous are distinct. Site credentials
  remain scoped and redacted; no silent profile/route downgrade. Personal login
  over Tor is not anonymity. No torrent-over-Tor default or Spotify decryption.
- **Updates (R01–R08):** installed/latest/compatible/checked/error/rollback states,
  integrity-verified pinned components, active snapshots, stable/development
  separation and tokenless public release checks. Stage before stop-coordinated
  replacement; preserve the previous installation, credentials and data.

## Nonfunctional and release acceptance

Measure 100/800/1,000/5,000 jobs plus repeated/long-lived cycles: latency, CPU,
RSS, threads, SQL, callbacks, cancellation, shutdown and independent persistence.
Synthetic completion is not freeze/leak freedom or a real authenticated transfer.
Native compact/standard/large/fullscreen Light/Dark/System visual and keyboard QA
is required; offscreen assertions alone do not establish native polish.

Use incremental typed components and existing bounded services, not a speculative
rewrite. Preserve settings/history/downloads/Keychain/native-host/extension IDs
during visible rebrand to MediaGrabber. Keep the Swift bridge branches intact.

No local admin/Apple licence-gated builds. Hosted native build/test only. The
preferred exFAT `dist/MediaGrabber.app` destination remains an unresolved install
requirement. Live private-site QA, release publication, protected merges and
installation require the user's explicit participation/approval.

## Programme

A verified baseline → B P0 queue/stability → C researched design/rebrand →
D real playback → E download capabilities → F onboarding/scoped auth →
G recoverable updates/distribution → H full end-to-end acceptance.
Continue independent unblocked work; do not call the whole product finished
until all acceptance criteria and explicit stable-release approval are met.

Source reconciliation: current mission, Reliable Downloads master, Critical UX
addendum and Product Quality steering are available and retained in the ledger.
Earlier migration instructions are represented by existing migration/context docs;
the current mission does not authorize resuming Swift development.
