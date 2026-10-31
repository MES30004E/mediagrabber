# Queue filtering and explicit selection scopes

## Intent and boundary

Finish Q04's discoverable large-queue selection controls on the existing native
model/view, without hidden-job action targets or a broad visual redesign. Existing
pause/resume/cancel/removal services consume selected UUIDs unchanged. Keep all
other backlog rows, auth/network/download persistence and protected branches.
Base4c3412422d1bfad7fa888b79e78a0c2f26bae9ab/run41206020420 is qualified.

## Approaches / engineering choice

Use a custom native QSortFilterProxyModel over immutable raw-status/search roles,
and compact native filter/selection controls. This keeps filtering separate from
queue execution and avoids per-keystroke reformatting of every source row. Reusing
rendered status text is unsafe because labels can be postprocess/error summaries;
rebuilding a second item table would reverse the model/ownership improvements.
Chosen under autonomous P0 instructions; this is not user approval of P1 redesign.

## User-visible contract

- Filters combine Media/Torrents/All, status category and literal case-insensitive
  search of title/site/source/original URL/destination. No regex execution or I/O.
- Status categories: All, Waiting, Running, Completed, Failed, Paused, Cancelled,
  Interrupted. Running includes Analysing/Downloading/Converting/Fetching metadata/
  Seeding; Completed includes Completed with warnings.
- Select menu: All queue jobs (show all), Filtered results, Visible rows, None,
  and status groups within current filtered results. All queue clears kind/status/
  search restrictions; filtered includes offscreen results; visible means rows
  intersecting the current viewport, including partial rows. None clears hidden
  remembered selection too. Every explicit selection replaces, not accumulates.
- Counts show actual selected, filtered shown and total. Hidden remembered IDs
  remain restorable across ordinary filter changes but cannot enter batch actions.
  Details/current target must reflect a visible selected job or be blank.
- Two compact rows use existing native controls/style at the900px minimum; no
  new theme/icon/web dependency. Search/status changes refilter the proxy only.

## Ownership / implementation

QueueRow adds immutable raw status and normalized search text. dataChanged includes
their roles so live changes update proxy membership. New queue_selection.py owns
status sets, proxy predicate and selection-range/viewport helpers, not backend or
database. UI owns filter widgets, remembered UUIDs, primary target and counts.

Filter changes block transient selection signals, apply the proxy change, restore
visible remembered UUIDs and reconcile details once. Source progress retains its
one-row presentation path; only membership changes need selection reconciliation.
Structural/model resets restore by UUID, never old row numbers. Explicit actions
clear hidden memory first and apply one batched QItemSelection. No per-job widgets,
threads, metadata requests or DB writes are introduced by filter/selection actions.

Use beginFilterChange/endFilterChange when both exist, otherwise invalidateFilter
for older supported Qt. Qt's official reference says begin since6.9/end since6.10;
invalidateFilter is scheduled deprecated6.13. Local6.11.2 has both. See
[Qt reference](https://doc.qt.io/qt-6/qsortfilterproxymodel.html) and
[PySide reference](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html),
retrieved2026-10-31. No claim every supported older runtime is executed locally.

## Acceptance and limits

TDD real source/proxy/selection tests: mixed kinds/statuses, literal metacharacters,
raw-vs-displayed status, live membership transitions, resets/removals, hidden memory
clear, viewport partial rows, all-vs-filtered scopes, counts/details and actual
batch action UUID targets.800/5000 selections must use bounded native ranges and
not reformat source rows on typing. Preserve existing tests and frozen matrix.
Capture/inspect actual offscreen compact/standard synthetic renders; not Cocoa/
fullscreen/professional design acceptance. Full Python/JS/drift/pipcheck, one fresh
independent review/fix pass and audited push/exact hosted qualification required.

No local Apple tools/admin, private accounts/media, release/upload/install. No
selection action deletes files or changes statuses itself. All publication gates
and existing external-volume/destination decisions stay unresolved as before.
