# Queue Collections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one fresh final review.

**Goal:** Durable groups, truthful progress/status totals and safe scoped clearing.
**Architecture:** pure indexed projections plus native list/proxy models; UI routes
scoped actions through existing QueueBatch/removal safety services.
**Tech Stack:** existing Python/PySide6/SQLite JSON; no new runtime/SQL schema.
**Spec:** docs/superpowers/specs/2026-11-01-queue-collections-design.md.

## Global Constraints

Base034efad618cf98aef633c267570954db963f064d/run41289264510 qualified. Same existing
checkout/development branch; protect main/Swift/provider/Oct drafts. No local
Apple tools/admin/private accounts/media/release/upload/install. Exact index/
history/provider/Public audit before each nonforce push; no live-run cancellation.

## Review Focus

- Same-title unrelated sources and legacy data must not merge by appearance.
- Progress/reset/remove/restart must retain accurate group membership and selection.
- Hidden filters/modal event races must not broaden destructive action targets.
- Group aggregation/search must not add N scans/workers/widgets per progress event.
- Untrusted labels, failed admission/persistence and partial owner shutdown must
  not invent success or delete unrelated/completed work.

### Task1: Persisted identity, pure aggregates and native models

Files: models.py; new queue_collections.py and collection_model.py;
queue_model.py/queue_selection.py; new tests/test_queue_collections.py and
tests/test_collection_model.py; database tests.
Interfaces: assign_collections(items)->list[(id,name)], collection_key(job)->str;
CollectionIndex.sync(jobs), update_job(job), summary(key), ids(key,status='All');
CollectionListModel.sync/update_job,row_for_id,summary; collection role in queue;
QueueFilterProxyModel.set_filters(kind,status,query,collection_id='').
- [x] RED new/legacy IDs, same-title separation, JSON/reopen/defaults/admission
  allocation without mutating items; implement payload fields/helpers; GREEN.
- [x] RED incremental category/progress/unknown/removal/membership/randomized
  invariants; implement O(1) updates and native model roles/thread guard; GREEN.
- [x] RED combined collection/kind/status/search and live UUID transitions;
  extend cached proxy/role; GREEN old/new selection/model tests.

### Task2: Native scopes and shared safe action execution

Files: ui.py; new tests/test_collection_ui.py; affected history/bulk/UI tests.
Consumes Task1; existing QueueBatch/FileRemoval/QueueRestart unchanged in purpose.
- [x] RED atomic enqueue groups/failed admission, reopening/restart membership,
  selector/summary/unknown progress/clear-all filters and no source scan on typing.
- [x] Add compact native collection/summary/actions; keep group selection by ID,
  update one aggregate per progress, show actual batch outcomes while totals update.
- [x] RED800/5000clear Completed/Cancelled/Failed/current collection and pause/
  resume/cancel scopes: one confirmation, keep default, hidden unrelated jobs safe,
  completion/modal/owner/DB-failure races. Route common removal executor and32-ID
  status actions; guard completed states on Cancel; GREEN old/new tests.
- [x] Capture/inspect900x650/1180x820actual frames; new controls fit; existing
  compact113px queue viewport/narrow cells and standard gap remain P1 work.
- [x] Explicit2Nov steering: restore direct Clear Completed on existing split
  button; make unknown progress counts visible without uncertain full bar.

### Task3: Native qualification and evidence

Files: queue_check.py/check_packaged_app.py + tests; architecture/backlog/scale;
new docs/QUEUE_COLLECTIONS.md.
- [x] RED missing/bad group evidence and nonworking scoped actions falsely passing;
  extend actual guarded two-cycle four-size probe, preserving all prior18records/
  selection/restart/worker/persistence/archive gates; GREEN.
- [x] Measure O(1) aggregate progress/filter observations and large-scope action responsiveness;
  document legacy grouping/average semantics and bulk summary deferral limits.
- [x] Full Python/JS/drift/pipcheck; one fresh read-only review, one Critical/
  Important RED→GREEN fix pass/full suite; defer minors; retain full backlog.
- [ ] Exact audit/coherent commits/nonforce development push, remote SHA and exact
  actual hosted macOS/Linux/frozen matrix/archive logs. No release or installation.

Self-review: Task1 allocation feeds Task2 atomic job saves; all models use identical
collection_key. Task2 currentData scope feeds Task3 actual controls. New payload
fields stay outside explicit Python/Swift protocol adapters/fixtures.
