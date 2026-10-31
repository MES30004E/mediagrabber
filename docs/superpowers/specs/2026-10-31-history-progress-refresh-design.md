# History progress refresh boundary

## Intent and constraints

The user clarified that the large-queue incident left the window open but frozen.
Do not describe it as a reproduced native crash. The queue model/header work and
frozen synthetic matrix are now qualified on053264c/run41172016114. Remaining
two-progress-callback profile at5,000 assigns0.530/0.537s to history refresh,
decoding10,000jobs and writing70,000cells. Stop doing unchanged history work on
the GUI thread while preserving persistence and all existing visible behavior.

Keep native Python/PySide6, existing checkout/main/Swift/provider/drafts and auth/
network/download behavior. No DB schema change, private data, Apple build tools,
admin, releases/uploads/install. Synthetic tests only; no skip-based acceptance.

## Approaches and engineering choice

- Chosen under the user's autonomous P0 instructions: immutable history-row
  presentation plus a small GUI-owned refresh state. Compare only the changed
  job's rendered/filter/order fields; skip history queries/cell replacement for
  bytes, speed, ETA and progress alone. Keep current SQL search/status semantics.
- Timer coalescing would still repeat unchanged full queries and widget work;
  adds latency/lifecycle state without eliminating the measured cause.
- Full history QTableView/model migration removes row objects too, but is a larger
  independent step. Do not conflate this hot-path correction with finishing that
  work, the media library/viewer or professional redesign.

## Boundary and correctness

New pure `history_presentation.py` contains immutable HistoryRow(job_id,
created_at,cells) and HistoryRefreshState. Cells exactly match current seven
history columns; raw created_at participates in equality because it affects SQL
ordering even when subsecond differences are not rendered. No Qt/backend/I/O.

`_refresh_history` still queries Database.search_history with identical arguments
and renders the same cells. It remembers **successfully rendered DB snapshots**,
not mutable/unpersisted values from unrelated self.jobs. Retain hidden snapshots
and prune removed IDs; filtered-out newly seen jobs may conservatively refresh
once, then be remembered after their successful save/refresh.

`_job_changed` always persists and refreshes queue/details as before. Only history
refresh is gated by immutable row equality. After a changed job's save and any
required history refresh succeed, remember that persisted snapshot even when
filtered out. On failure do not acknowledge it. New jobs, title/URL/output/format/
status/order changes still refresh. Explicit search/filter/structural operations
remain immediate. Never defer state in a timer or update Qt from a worker.

Review refinement: full refresh starts dirty and only success clears it, so failed
explicit filter/query/render changes retry even when the next callback row is
unchanged. All successful non-callback visible-lifetime writers invalidate too;
small status actions/watchdog/restart/stop-seeding refresh once, dispatch and batch/
cleanup use their next callback/completion boundary. Closing-only persistence
does not render. A committed callback metadata change invalidates before queue
rendering, so queue-render failure cannot suppress another callback's retry.

## Proof and non-goals

TDD: progress-only callbacks preserve history item identities/selection and issue
zero history queries while DB progress updates remain current. In-place metadata
changes, hidden→matching status/search, raw ordering changes, new/removal and
failed refresh retry must remain correct. An unpersisted mutation of a different
job must not be falsely acknowledged by another job's refresh. Existing SQL LIKE
wildcard/case behavior and context-menu stable job IDs remain unchanged.

Paired source synthetic100/800/1000/5000 before/after measurements use the same
053264c fixture and toolchain. Full Python/JS/drift/pip checks, one independent
final review/Important fix pass, secret audits/Public verification and exact new
hosted native qualification follow. Preserve all existing native gates. RSS and
heartbeat observations do not prove leak freedom or live-account acceptance.
