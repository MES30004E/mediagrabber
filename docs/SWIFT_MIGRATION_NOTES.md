# Future Swift migration constraints — not a migration design

Stage 1 establishes the current Python/PySide6 behavioural reference. This file
records constraints for a later separately authorized Cloud task. It does not
choose a final backend, specify IPC, create Swift source, move the Python layout,
or implement Swift/migration CI.

## Non-negotiable boundaries

- Preserve the Python implementation until a future native version demonstrates
  behavioural parity. Avoid a big-bang rewrite or cosmetic repository moves.
- Do not rewrite yt-dlp extraction in Swift. Retain ffmpeg/ffprobe, aria2c, and
  upstream bgutil behaviour where needed; they are distinct engines.
- Future SwiftUI work may own UI/state presentation, native menus, Finder,
  Keychain, and lifecycle integration. This is intended scope, not an approved design.
- Structured progress is a contract to preserve. Do not make human-readable
  yt-dlp console text the primary native frontend API.
- Compare retained Python API worker, structured yt-dlp subprocess, and hybrid
  boundaries against the actual application before selecting an architecture.
- Keep authentication and routing composable. Private media requires authorised
  cookies, never cache scraping, decryption, account bypass, or private CI data.
- No new identity-changing/restriction-evasion loops; separately review the
  baseline's existing limited automatic Managed Tor circuit retries.

## Behaviours the future design must account for

Read the actual functions/tests in `CURRENT_ARCHITECTURE.md`, especially:

- URL versus text search; exact `:ytwatchlater`, canonical Watch Later URLs,
  ordinary playlists and watch URLs with playlist context.
- Authenticated analysis and per-item downloads, public-first Auto, explicit
  cookies, private/account-required failure rules, and safe diagnostics.
- Playlist expansion/indexing, preview selection, and candidate matching.
- Stable job IDs, live Queue selection, SQLite history, interrupted-job recovery.
- Distinct Resume/Retry/Restart and exact file ownership before removal.
- Playable format selection, quality fallbacks, QuickTime compatibility,
  stream copy versus transcode, subtitles/artwork/chapters and output verification.
- Runtime snapshots, verified updates, provider compatibility and rollback.
- Proxy socks5h DNS, app-owned versus external Tor, isolated process lifecycle.
- Separate torrent engine, magnet metadata, selection, private trackers, and no Tor for peers.
- Spotify metadata-only matching, redacted Console/logs, Keychain storage, Finder actions.

Not every current behaviour is desirable: distinguish intended contracts from
known defects before turning them into parity requirements. In particular,
review candidate auto-enqueue, login-test routing, cancellation gaps, and Tor
retry policy rather than reproducing them without a decision.

## Native development constraint

The local Mac cannot accept the Xcode licence and has no admin access. Do not
run local Xcode, xcodebuild, xcrun, sudo, or licence acceptance. This is not a
source-development blocker. Codex Cloud is not assumed to run macOS.

The intended later validation path is Cloud source editing → GitHub → hosted
macOS CI → native build/tests. Early native tests should not need private
credentials or signing/notarisation. This baseline does not add that workflow;
its detailed design requires the next task's explicit authorization.

## Stage 1 handoff gate

Before migration design, confirm the private repository contains the baseline,
check out its pinned provider submodule, provision suitable test tools, and
rerun tests. The dated Stage 1 local result is 222 passed; do not claim Cloud
test parity or live private-account success from that number alone.

An appropriate next request is: inspect the Python baseline and existing
context documents, establish Cloud test prerequisites, then propose a gradual
migration design for review without deleting Python or requiring local Xcode.
