# History Progress Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one final independent review.

**Goal:** Eliminate unchanged full-history work from progress callbacks without
changing SQL/history/persistence/downloader behavior.
**Architecture:** pure immutable history presentation/refresh state; MainWindow
still owns Qt and calls existing DB query for real presentation changes.
**Tech Stack:** existing Python3.12/PySide6/SQLite; no new dependency/schema.
**Spec:** `docs/superpowers/specs/2026-10-31-history-progress-refresh-design.md`.

## Global Constraints

Existing checkout/branch; preserve main/Swift/provider/drafts. No private accounts,
Apple tools/admin/release/upload/install. Every push allrefs/provider/index audit
and Public verification; no force. Prior053264c exactrun41172016114allgreen.

## Review Focus

- In-place mutable jobs incorrectly compared to themselves, hiding metadata.
- Filtered-out jobs cause endless refresh or fail to reappear when matching.
- Another job's unpersisted changes are mistakenly remembered as rendered.
- Failed DB/presentation refresh acknowledges stale state and suppresses retry.
- SQL search/order/context-menu IDs or persisted progress change inadvertently.

### Task1: Pure history snapshots

Files: create `src/morgan_media_downloader/history_presentation.py`,
`tests/test_history_presentation.py`.
Interfaces: frozen HistoryRow(job_id:str,created_at:str,cells:tuple[str,...]);
`history_row(job:DownloadJob)->HistoryRow`; HistoryRefreshState.needs_refresh(row),
remember(row), rendered(rows,existing_ids). State stores immutable snapshots;
rendered merges only DB-derived visible rows and prunes IDs no longer existing.
Review refinement adds invalidate(): dirty until full successful render; remember
alone cannot clear it. All successful non-callback UI writers invalidate.
- [x] RED exact seven cells and equality unaffected by progress/speed/bytes/ETA;
  raw created_at ordering, status/title/URLs/output/effective format change it.
  State detects in-place mutation, retains hidden rows, prunes removed IDs.
- [x] Implement pure boundary; GREEN focused tests (no Qt/DB/worker changes).

### Task2: UI hot path and regression proof

Files: modify `ui.py`, create `tests/test_history_progress.py`.
Consumes Task1. Initialise state before UI construction; full history formats
through history_row and records DB rows only after all cells successfully render.
`_job_changed` saves first, compares one row, conditionally refreshes history,
remembers only after success. Preserve queue/details and SQL query arguments.
- [x] Capture paired source baseline100/800/1000/5000 before implementation.
- [x] RED actual window two progress callbacks perform zero search_history calls,
  preserve selected row/item identities, and persist changed progress/bytes.
- [x] RED in-place metadata, hidden→matching filters/SQL LIKE semantics, new/removal,
  raw ordering, failed-render retry, and unrelated unpersisted mutation isolation.
- [x] Minimal integration; GREEN all targeted and existing history/UI tests.

### Task3: Evidence and publish

Files: FEATURE_BACKLOG/CURRENT_ARCHITECTURE/QUEUE_SCALE; existing workflow retained.
- [x] Paired after matrix, full Python/JS/drift/pipcheck; one fresh read-only review
  and one Important/Critical RED→GREEN/full-suite fix pass, minors deferred.
- [x] Document user freeze clarification and prior exact native matrix/archive;
  retain every unfinished requirement, memory/long-gap/live QA limitations.
- [ ] Review diff/index, audit all refs/provider/exact index/Public/protected refs;
  coherent commit/nonforce push, verify remote and actual exact hosted results.

Ruling: autonomous small behavior-preserving performance correction; no broad UI
redesign or additional approval-dependent deployment. Cost if wrong: presentation
could stale; immutable/failure/filter regressions and hosted checks are gates.
