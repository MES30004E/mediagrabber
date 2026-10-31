# Queue Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one final independent review.

**Goal:** Filter/select large queues with truthful scopes/counts and stable action IDs.
**Architecture:** immutable model roles + flat native proxy/selection helpers;
existing UI owns widgets/UUID memory; execution/persistence unchanged.
**Tech Stack:** existing Python/PySide6; no dependency/schema change.
**Spec:** `docs/superpowers/specs/2026-10-31-queue-selection-design.md`.

## Global Constraints

Same checkout/development branch; protect main/Swift/provider/Oct drafts. No
Apple tools/admin/private accounts/media/releases/uploads/install. Every push
allrefs/provider/exactindex audit/Public verification, no force or live-run cancel.
Existing qualified base4c34124/run41206020420; broader backlog remains active.

## Review Focus

- Hidden selected IDs accidentally enter destructive actions or resurrect after None.
- Live status/search changes corrupt selection/current details or act on wrong row.
- Filtering reintroduces full-source formatting/work on every keystroke/progress.
- Viewport edges, zero rows and status groups misreport or over-select targets.
- Qt version fallback, menu closure binding and compact layout break real controls.

### Task1: Model roles and proxy/selection helpers

Files: queue_model.py; new queue_selection.py; new test_queue_selection.py.
Interfaces: STATUS_ROLE/SEARCH_ROLE return raw string status/normalized search;
QueueFilterProxyModel.set_filters(kind:str,status:str,query:str); status_matches;
select_rows(view,rows), visible_rows(view), restore_ids(view,source,ids)->tuple[str,...].
- [x] RED source roles/proxy AND filtering, literal casefold, completed/running
  categories, live updates and invalid filters refused before mutation.
- [x] Implement immutable fields/roles and native custom predicate; capability-
  gated filter-change API; GREEN real source/proxy model tests.
- [x] RED range/viewport/UUID restore including zero/partial/offscreen rows;
  implement bounded helpers; GREEN.

### Task2: Native controls and action integration

Files: ui.py; new test_queue_selection_ui.py. Consume Task1.
- [x] RED actual Select actions/scopes, counts, hidden memory None/replace,
  status filters, source not reformatted on search, current/details reconciliation.
- [x] Add search/status and compact Select/count/clear rows; proxy-only filter
  refresh; stable UUID reconciliation after structural or live membership change.
- [x] RED mixed filtered800/5000 selection and real pause/cancel/removal action
  target IDs, one keep-files confirmation; implement minimal glue; GREEN old/new UI.
- [x] Capture and inspect compact/standard synthetic renders; fix measured clipping
  with regression if needed. No P1 polish/Cocoa/fullscreen acceptance claim.

### Task3: Evidence, review and qualification

Files: FEATURE_BACKLOG/CURRENT_ARCHITECTURE/QUEUE_SCALE and selection usage doc.
Also extend existing queue_check.py/check_packaged_app.py and their tests: both
cycles trigger real selection actions/filter changes, independently compare
viewport UUIDs, and require count/hidden-clear/zero-SQL/zero-worker evidence.
Keep all18existing measurement records, persistence/worker and archive gates;
additional control/column roundtrips mean no direct prior timing comparison.
- [x] Record prior4c exact hosted evidence; keep all unfinished requirements.
- [x] Full Python/JS/drift/pipcheck, one fresh read-only review; one Important/
  Critical RED→GREEN fix pass/full-suite, minors deferred.
- [ ] Diff/index/secret/Public/protected-ref audit, coherent commit/nonforce push;
  verify exact remote SHA and actual hosted alljobs/native matrix/archive results.

Ruling: viewport-only vs filtered/all scopes are explicit engineering defaults,
not a change to batch execution or permission for hidden destructive targets.
Cost if wrong: users may expect another scope; clear labels and ID/action tests
make selection inspectable and reversible before existing confirmation dialogs.
