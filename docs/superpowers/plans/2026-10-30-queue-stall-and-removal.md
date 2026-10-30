# Queue Stall and Single-Confirmation Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans inline; preserve the active hosted packaging run and existing checkout. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the measured eager-header queue stall and confirmed per-item removal prompts without claiming the entire large-queue architecture is complete.

**Architecture:** Retain the current queue for this narrow root-cause fix. Use user-resizable columns with one explicit content-size pass after structural changes, not eager resizing on each status-cell mutation. Snapshot the selected jobs and obtain one native keep/delete/cancel decision; active job removal remains deferred to the existing owned-worker completion path. Broader bounded batch services/model-view/DB batching remain separate P0 work, not omitted.

**Tech Stack:** Python/PySide6, QHeaderView, QMessageBox, existing file ownership/TaskManager/SQLite, isolated child-process diagnostic.

**Spec:** `docs/FEATURE_BACKLOG.md` Q01–Q11 and `docs/QUEUE_SCALE.md`; user Critical UX/Scalability Addendum. The user explicitly authorized autonomous incremental fixes and forbids a speculative whole rewrite. The major visual redesign still requires actual mockups and approval later.

## Global Constraints

- No personal sessions/media, real downloads, Apple build tools, installation or release publication.
- Preserve main/Swift/provider and unrelated drafts; stay in current development checkout.
- No conflicting push while hosted run40991415616 is active.
- Keep files is the default; delete only through existing job-owned-file helper after worker stop.
- Never describe a responsive synthetic run as proof of the still-unreproduced native crash's cause.

## Review Focus

- One selected snapshot/one confirmation; cancellation leaves all jobs untouched, including active ones.
- Default button really keeps files; status summary includes actual completed and active counts.
- Active removal remains pending until task finishes; no filesystem deletion while its worker runs.
- Column sizing does not perform every-row measurement for every changed cell; scroll/selection/filter and user-resizable columns remain usable.
- 5,000-item timeout must become a measured result or remain an explicit blocker, not be omitted from reports.

### Task 1: Reproduce and measure

**Files:** `scripts/benchmark_queue.py`, `tests/test_queue_scale_probe.py`, `docs/QUEUE_SCALE.md`.
**Interfaces:** CLI emits JSON per isolated size; real MainWindow/DB/actions, synthetic workers and intercepted modal choices. Capture CPU/RSS/native thread samples/active tasks/heartbeat/SQL and bounded timeout diagnostics.

- [x] Run baseline100/800/1,000/5,000; record failures/timeouts and code profile. Evidence is in QUEUE_SCALE.md.
- [x] Single-variable diagnostic: suspend auto header sizing only during pause. At800, pause drops from14.812s to0.120s including profiler, whereas unchanged resume/cancel remain15.773/19.149s. This identifies the measured stall mechanism, not the native crash.
- [x] Run the diagnostic regression; whole suite602passed before production fixes.

### Task 2: Narrow root-cause corrections

**Files:** `ui.py`, `tests/test_queue_bulk.py`.
**Interfaces:** `_confirm_remove(jobs: list[DownloadJob]) -> str` returns list/delete/cancel once for the snapshot. Existing pending-removals bool contract and ownership helper stay intact. Non-stretch columns remain Interactive, with explicit structural-only sizing.

- [ ] Observe RED: 800-item removal prompts800times; status cell changes see eager ResizeToContents mode. Bulk cancel already has a preservation assertion.
- [ ] Use one dialog/count/default keep decision and one post-loop status; preserve deferred active removal. Add real dialog-button/default/count and active-removal regressions.
- [ ] Disable eager content sizing; explicitly size nonstretch columns once per structural refresh. Observe GREEN behavioral layout assertions, then full suite.
- [ ] Rerun identical four-size probe; update before/after table and retain unqualified/crash/UI/batch architecture gaps.

### Task 3: Review, checkpoint and retain priority

**Files:** backlog/QUEUE_SCALE and tests above.
**Interfaces:** no new runtime/DB schema/service contract in this checkpoint.

- [ ] Read-only focused review once; Important/Critical reproductions RED→GREEN, full Python/JS/drift verification.
- [ ] Commit coherent queue checkpoint locally. Audit all refs/provider/exact index and Public visibility before a later development push, only after live packaging run terminates.
- [ ] Inspect hosted packaging outcome separately; no public release qualification claim from queue tests.
