# Queue search, status and selection

The Queue page uses the existing native model/view. These controls do not analyse
media, start downloads, attach credentials or write the job database.

## Filters

View chooses Media, Torrents or All. Status and search combine with that view.
Search is literal, case-insensitive text across title/site, source/original URL
and destination; regex characters have no special meaning. Authentication paths
and browser profiles are not indexed. Running includes analysis, transfer,
conversion, metadata fetch and seeding; Completed includes warnings. Interrupted
has its own category. Clear filters reveals the whole queue.

## Select menu

| Action | Scope |
| --- | --- |
| All queue jobs (show all) | Clears filters and selects every queued job |
| Filtered results | Every matching row, including results below/above the screen |
| Visible rows | Only rows intersecting the current table viewport, including partial edge rows |
| None | Clears both displayed selection and hidden remembered selection |
| By status in filtered results | Selects that status category only within the current results |

Explicit menu actions replace selection. Normal filter changes remember UUIDs
for a roundtrip, but hidden remembered rows cannot enter Pause/Resume/Cancel/
Remove. Counts show selected, shown and total; always inspect the selected count
before a batch action. Filtering to zero shows a matching-results message rather
than claiming the entire queue is empty. Details describe a visible selected job
or clear; removing the primary selection chooses a surviving visible selection.

Existing queue actions retain their existing safety rules: keep-files removal is
the default, file deletion remains separately confirmed and job-owned, and bounded
batch processing takes its own ID snapshot. Collections, bulk restart, dedup and
interruption recovery are separate unfinished work, not supplied by this menu.

## Implementation and evidence

`queue_model.py` provides immutable raw status/search roles. `queue_selection.py`
owns the flat proxy predicate and range/viewport/UUID helpers. Search/status changes
refilter cached roles without formatting all source jobs; changing View still
re-presents its different columns. Live changes reconcile selection by UUID, not
row position. GUI-owned mutations remain separate from workers and persistence.

Source tests cover literal/combined/live filtering, optional metadata, version-
capability fallback, thread ownership, hidden selection, exact action IDs and
800/5000-job keep-file removal. The fallback is simulated on current Qt, not a
claim that every supported older binary was installed/tested.

Isolated source observations,1180x820/Light, already in All view; each includes
event processing/repaint, not a hard latency budget:

| Items | Search ms | Status filter ms | Select filtered ms | Select all ms | Current RSS MiB |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 |4.98|4.39|4.80|6.09|133.73|
| 800 |8.99|9.61|5.40|17.26|148.34|
| 1000 |10.03|11.24|5.68|19.61|152.66|
| 5000 |36.62|89.77|12.21|83.68|227.30|

All cases reformatted zero source rows during these same-view operations, created
zero owned tasks and sampled8native threads; visible selection chose9rows. This
does not measure the first View column switch, real transfers or long-run memory.
Actual900x650/1180x820offscreen captures were inspected; controls fit. Compact
title/destination elision and wider design/theme issues remain P1; no Cocoa,
fullscreen, dark-theme or professional-redesign acceptance is implied.

The existing frozen queue diagnostic now exercises real QAction/filter scopes
after enqueue in both cycles, independently compares viewport geometry UUIDs,
checks hidden-memory clearing, restores Media view and requires zero SQL/owned
tasks from selection. The verifier rejects missing/partial/wrong evidence. Its
original18stage records and worker/persistence/archive checks remain; added column/
filter roundtrips change fixture costs, so do not compare its new timings directly
to older runs. Exact new hosted qualification is required after audited source push.

Qt API choice is grounded in the [official C++ reference](https://doc.qt.io/qt-6/qsortfilterproxymodel.html)
and [PySide reference](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html),
read2026-10-31 using the documentation skill. New begin/end filter-change methods
are capability-gated, retaining the older invalidateFilter fallback.
