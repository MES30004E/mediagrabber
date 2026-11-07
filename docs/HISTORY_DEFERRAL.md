# Hidden History refresh deferral

Mission B3, narrow P0 correction. The real `_refresh_history` path queried all
matching persisted jobs and rebuilt seven QTableWidget cells per row even when
the user was on Queue. A prior whole-fixture profile attributed4.43s/20calls to
this real path; the separate12.65s diagnostic `verified_reload` comparison is
not application work and has not been removed to make results look better.

## Behavior and boundaries

- `_refresh_history` invalidates presentation, then avoids querying/rendering
  unless the actual History page is selected. Hidden explicit refreshes discard
  obsolete rows/snapshots rather than retaining them through load/clear cycles.
- Navigation invokes `_render_pending_history` without invalidating a clean view.
  Clean revisits preserve cell objects and selection. Use page identity, not a
  fixed navigation index or top-level widget visibility during construction.
- Only successful render clears pending state. Query/render failures remain
  retryable; a late refresh/navigation signal after close cannot query the DB.
- A persisted callback is remembered only after successful presentation. Hidden
  invalidations coalesce; unsaved mutable jobs never substitute for database rows.
  Persisted but filter-excluded callbacks retain their existing visible behavior.
- SQL LIKE/status filters, indexed creation ordering, actual persistence and
  visible synchronous refresh semantics are unchanged. No new timer, worker,
  database schema, downloader or authentication behavior.
- This does **not** make opening or updating a large visible History view cheap.
  The first explicit hidden invalidation after a render still destroys existing
  cells once. Bare state invalidation (such as dispatch) defers presentation but
  does not release old cells until a refresh/revisit. No global constant-time,
  zero-retention, leak-free or production-freeze resolution claim is made.

## Tests and observations

New actual-window tests: startup/hidden query avoidance, latest filter coalescing,
clean-revisit selection/items, persisted versus mutable state, five hidden
load/clear cycles, query/render retry and close guarding. **6RED/2pass1.43s →
48 History tests passed4.57s**. Existing history-progress fixture now explicitly
selects History; all prior SQL/selection/failure assertions remain unchanged.

Expanded native Cocoa group (themes, queue, scheduler, restart and History):
**178 passed, five existing test-only warnings in50.97s**. Full isolated local
suite: **1,063 passed, five existing test-only warnings in153.09s**, no skips.
Independent review found no blocker; independently8tests passed1.20s. JS10/no
skips, protocol9fixtures and pipcheck pass. Exact hosted qualification is pending.
No new visual layout is claimed. Full command: `QT_QPA_PLATFORM=offscreen
.venv/bin/python -B -m pytest -q -p no:cacheprovider` with isolated temporary
MORGAN_DATA_DIR/MORGAN_LOG_DIR/MORGAN_CACHE_DIR; native group matches the expanded
`Native Cocoa UI correctness regressions` workflow step with platform=cocoa.

Paired fresh-process synthetic actual-window probe, five explicit hidden refreshes
per size, real temporary SQLite, blocked network/process/Keychain operations;
no concurrent performance run. Median wall milliseconds:

| Jobs | Before → after | SQL queries over five calls | Cell writes over five calls |
| ---: | ---: | ---: | ---: |
|100|5.647 →0.0025|5 →0|3,500 →0|
|800|53.984 →0.0011|5 →0|28,000 →0|
|1000|70.212 →0.0016|5 →0|35,000 →0|
|5000|379.260 →0.0013|5 →0|175,000 →0|

The hidden table held0rows afterward, compared with Nbefore; zero external calls
and owned workers in both probes. These timings reflect eliminated work, not a
timing-based test gate or a measurement of first stale-table destruction. Ignored
`history_hidden_probe.py` and `history-hidden-{before,after}.json` retain evidence
under `.superpowers/sdd/2026-11-02-ui-correctness/`.
