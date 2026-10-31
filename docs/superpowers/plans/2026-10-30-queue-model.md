# Queue Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline, test first; one final independent review.

**Goal:** Replace queue-only item/widget storage with a GUI-owned incremental model, native proxy and painted progress, preserving queue/backend contracts.

**Architecture:** `queue_model.py` owns immutable cached presentation rows and delegate;
`display_format.py` shares existing byte/duration formatting without UI imports.
MainWindow owns actions, selection and model synchronization; source/proxy IDs
remain stable across updates. No persistence or transfer worker moves into model.

**Tech Stack:** Python3.12, PySide6 6.11.2-compatible Qt model/view, pytest/offscreen.

**Spec:** `docs/superpowers/specs/2026-10-30-queue-model-design.md`.

## Global Constraints

Stay existing development checkout; preserve drafts/main/Swift/provider pins.
No local Apple build tools/admin/personal credentials/media/release/install.
No DB or auth changes; no whole-app redesign; native PySide6 remains.
No6.12-only APIs; audit histories/provider/exact index/Public before push.

## Review Focus

1. In-place mutation must not evade cached presentation change detection.
2. Proxy selection/reorder/filter must never change which jobs actions target.
3. Incremental row removal/insertion must satisfy Qt persistent-index contracts.
4. Invalid progress, hidden kinds and empty data must not crash delegate/model.
5. Targeted progress must preserve details/scroll and avoid all-row notification.

### Task1: Model, formatting and delegate

Files: create `src/morgan_media_downloader/queue_model.py`, `display_format.py`,
`tests/test_queue_model.py`. Extract existing human_bytes/human_duration unchanged.
Interfaces: `QueueTableModel.sync(jobs,view,connection_mode)->bool` reports structural
change; `update_job(job,connection_mode)->bool` reports known-ID admission;
`index_for_id(id)->QModelIndex`; UserRole ID, UserRole+1 kind, UserRole+2 progress.
Columns/view remain existing literal layouts. `QueueProgressDelegate.paint` uses
native style only for progress cells and delegates all other roles to Qt.
- [ ] Write missing-module RED tests for literal columns/values, source/proxy IDs,
  in-place mutation notifications, unchanged silence, contiguous insert/remove,
  reordered IDs/empty transitions with QAbstractItemModelTester Fatal mode.
- [ ] Implement minimal model/cache, GUI mutation guard and style delegate.
- [ ] Add invalid progress and real painted-image/zero-editor tests; observe RED
  before their production handling. Run focused model tests GREEN.

### Task2: Connect native queue without compatibility shims

Files: modify `ui.py`, `tests/test_ui_diagnostics.py`, `tests/test_queue_bulk.py`;
new `tests/test_queue_model_ui.py`. Keep tests about behavior, not QTableWidget APIs.
Consumes Task1 model IDs/roles/sync/update; produces existing MainWindow actions
with QTableView/QSortFilterProxyModel, stable multi-ID selection and details.
- [ ] RED:800rows have zero QProgressBar children, row data/details/progress intact;
  multi-selection persists through insertion/removal/view changes; actions target
  IDs after filtering; one-job callback emits only its row. Retain all bulk tests.
- [ ] Connect model/proxy/delegate; port old headers/progress identity assertions
  to real model/delegate behavior, not a production test-only adapter.
- [ ] Preserve scroll and selected details; bound structural header sizing sample.
  Remove old full item-building loop and import shared formatters.
- [ ] Focused tests GREEN, then full project suite GREEN.

### Task3: Evidence, review and publication

Files: update FEATURE_BACKLOG, QUEUE_SCALE, CURRENT_ARCHITECTURE; benchmark/test
changes only if required to measure the real model behavior.
- [ ] Run identical100/800/1,000/5,000 matrix, normal and synthetic cleanup; record
  actual RSS/CPU/heartbeat/widget counts, no fabricated native crash claim.
- [ ] Full Python, JS10, drift9, pip check; independent read-only final review;
  one Important/Critical fix pass with observed RED→GREEN and green full suite.
- [ ] Review status/diff/check/index and scan all history/provider/exact index;
  verify Public and protected refs. Commit coherent checkpoint, authorized push
  only development branch; verify SHA and actual hosted jobs/logs. No release.

Ruling: no plan-approval pause because the user requested autonomous implementation
of this exact P0 goal; nontechnical design approval remains required before the
separate professional visual redesign. Cost if wrong: queue behavior regression,
bounded by regression tests, independent review and rollback source point.
