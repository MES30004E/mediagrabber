# Queue model and bounded presentation checkpoint

## Intent and evidence

Preserve the existing native queue and backend behavior while removing its
per-row Qt items/progress widgets. The preceding423160a checkpoint passed hosted
41034253375, but5,000 synthetic items still reached~414MiB peak process RSS.
This is evidence for model/delegate work, not a reproduced native crash.

## Approaches and decision

- Retain QTableWidget and replace only progress widgets: smaller patch, but still
  allocates cells and couples UI ownership to data. Does not address incremental
  model updates or stable proxy selection well.
- Use QTableView/QAbstractTableModel, style-painted progress and a native proxy:
  selected engineering approach under the user's autonomous P0 instructions.
  Removes queue item/widget allocation, isolates presentation, and supports stable
  IDs. Requires porting tests from widget-specific APIs to behavioral model APIs.
- Do not replace history/playlist or redesign the whole app in this checkpoint.
  Their allocations remain measurable debt; no claim of total memory bounding.

## Contract

Queue model owns immutable presentation rows, never transfer workers, settings,
credentials or database writes. IDs are UserRole on model indexes. Preserve all
Media/Torrents/All columns, statuses/warnings, tooltips, progress precision,
details, selection, scroll and existing queue action semantics. GUI-only mutation.
Append/remove use incremental begin/end notifications; same-shape progress updates
emit only changed rows. Rare reorder/column-layout changes may reset, with stable-ID
selection restoration in UI. A source/proxy mapping must never turn a selected row
number into a different job. No N progress widgets or persistent editors.

Single-job progress uses a targeted model update rather than rebuilding every
queue row. Full bulk refresh remains available; unchanged rows emit no changes.
History refresh and DB progress writes are deliberately unchanged and remain debt.
Use native style painting, not a visual redesign. Existing header/row styling and
actions remain; no new cloud service, web framework, Swift work or DB migration.

## Constraints and acceptance

Local PySide6 6.11.2 and hosted6.12 must both work; do not use the6.12-only
dataChangeRelevanceFlags API. Preserve user drafts/main/Swift/provider pins.
No local Apple build/signing tools, personal sessions/media, release or install.
Keep filesystem destination unresolved. Audit all refs/provider/index/Public
before any authorized development push; no force or push over a live workflow.

Tests: real QAbstractItemModelTester, incremental rows/identity/roles/statuses,
unchanged and targeted notifications, reorder/filter/removal multi-selection,
scroll/details and all existing batch lifecycle tests. Render real delegate into
an image; assert no queue QProgressBar children at800/5,000. Full Python/JS/drift,
same100/800/1,000/5,000 benchmark matrix with before/after CPU/RSS/heartbeat/widgets.
One independent final review/fix pass; exact hosted native validation after push.
Native crash, real transfer/Trash/memory leak/Cocoa-scale acceptance remain open.

## Official references retrieved30 October2026

- [QAbstractItemModel](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractItemModel.html): GUI-thread API, begin/end rows and dataChanged.
- [QStyledItemDelegate](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QStyledItemDelegate.html): paint/sizeHint and current-style painting.
- [QSortFilterProxyModel](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QSortFilterProxyModel.html): source/selection mapping; rolling docs include6.12-only APIs absent locally.

Rollback point:423160a8e07a8fcd19c1c18950b2c5ebb44de337; no automatic reset or revert.
