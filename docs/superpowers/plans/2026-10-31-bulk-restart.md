# Bounded Bulk Restart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one final fresh review.

**Goal:** One explicit, bounded, failure-safe restart of selected jobs.
**Architecture:** queue_restart.py owns pure snapshot preparation and a GUI-owned
controller; existing TaskManager/QueueBatch own threads/backpressure; UI glue only.
**Tech Stack:** existing Python/PySide6/SQLite, no dependency/schema changes.
**Spec:** docs/superpowers/specs/2026-10-31-bulk-restart-design.md.

## Global Constraints

Existing checkout/development branch, no reset/force/main merge/Swift changes.
No local Apple tools/admin/private accounts/media/release/upload/install. Exact
index/allrefs/provider/Public audit before every push. Preserve October drafts.
Base72fd947f1c1a2d2ea076ad1af520369f0e3c6843/run41210675065 qualified.

## Review Focus

- Late transfer files or modal reentrancy must not bypass owner drain/confirmation.
- Interrupted preparation must commit before cleanup; final failure cannot dispatch.
- Keep must not overwrite torrent/media final outputs on later execution.
- Stop/shutdown/error callbacks must settle once without leaking or starting slices.
- Missing/unexpected result IDs and removal precedence must not publish wrong jobs.

### Task1: Restart policy and bounded controller

Files: new src/morgan_media_downloader/queue_restart.py, tests/test_queue_restart.py.
Interfaces: restart_job(job,choice,*,cleaner=None)->DownloadJob; RestartResult
(job_id,job=None,error=''); QueueRestart(manager,batch,database,jobs,active,excluded,
parent=None,*,processor=None), persisted signal, pending map; start(ids,choice),
owns(id), owner_stopped(id), close()->list[DownloadJob].
- [x] RED keep/replace owned-file outcomes, foreign/missing paths, fresh child
  destinations for media/torrent, reset/auth preservation and invalid choices.
  Expected: missing module. Implement policy; GREEN real temporary files.
- [x] RED slice/owner/latest-inventory/prepared-commit/final-failure/worker-exit/
  redaction/Stop/close tests using real DB/TaskManager/QueueBatch. Implement
  controller, no per-job threads; GREEN tests/test_queue_restart.py.

### Task2: One native confirmation and integration

Files: ui.py; new tests/test_queue_restart_ui.py; affected history/bulk tests.
Consume Task1; preserve action/history/removal safety paths.
- [x] RED800/5000actual selected targets/one confirmation, default Keep dialog,
  cancellation, no selection, real thread responsiveness, active latest inventory,
  pending removal wins and shutdown persistence. Expected old per-job behavior.
- [x] Replace legacy GUI cleanup loop with controller; one dialog with metadata
  counts, native safe default and explicit replace. Owner completion notifies
  controller, persisted signal invalidates history; close retains uncertainty.
  GREEN old/new UI/bulk/history tests; adapt only synchronous restart assumptions.

### Task3: Native evidence, documentation and qualification

Files: queue_check.py/check_packaged_app.py + tests; FEATURE_BACKLOG,
CURRENT_ARCHITECTURE, QUEUE_SCALE; new docs/BULK_RESTART.md.
- [x] RED missing/bad restart evidence and nonworking restart controls falsely
  passing. Extend both cycles before transfers with real controller/worker,
  guarded empty-inventory cleanup, committed verification and strict result gates.
  Keep all existing18measurements/selection/worker/archive checks.
- [x] Record paired old/new synthetic restart responsiveness, source scale and
  actual dialog capture; preserve all backlog items and exact72fd947 evidence.
- [x] Full Python/JS/drift/pipcheck; one fresh read-only final review, one
  Critical/Important RED→GREEN fix pass/full suite; defer minors.
- [ ] Audit exact index/history/provider/Public/protected refs; coherent commit,
  nonforce development push; verify remote and exact hosted results. No release.

Self-review: Task1 owns all persistence/thread transitions; Task2 consumes its
ownership signal after active.pop; Task3 exercises exactly that public interface.
