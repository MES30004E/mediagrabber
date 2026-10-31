# Native Queue Diagnostic Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one final independent review.

**Goal:** Exercise the actual frozen Cocoa GUI with synthetic large queues and truthful bounded evidence, not only an empty startup window.

**Architecture:** share real queue exercise in `queue_check.py`; existing source
benchmark/startup diagnostic own fresh state and QApplication; packaged verifier
validates exact cycle evidence and bounded reports. No normal UI/backend changes.

**Tech Stack:** Python3.12, existing PySide6/TaskManager/SQLite, hosted macOS.
**Spec:** `docs/superpowers/specs/2026-10-31-native-queue-diagnostic-design.md`.

## Global Constraints

No local Apple build tools/admin/personal data; no releases/uploads/install.
Preserve checkout/drafts/main/Swift/provider. No superseding push over live41169869112.
No real network/Keychain/filesystem deletion; disposable root only, anonymous auth.
Old benchmark/startup contracts and all tests retained; no skip-based qualification.

## Review Focus

- Diagnostic accidentally touches existing state or lets real transfer escape.
- Synthetic worker ownership or failed cancellation is reported as completion.
- A partial/spoofed report with correct outer flags bypasses actual scale evidence.
- Native failure or timeout hides evidence or dumps credential-bearing logs.
- Refactoring benchmark changes measured stages or leaks global patches/timers.

### Task1: Shared real queue exercise

Files: new `src/morgan_media_downloader/queue_check.py`; modify
`scripts/benchmark_queue.py`; tests `test_queue_check.py`, existing scale tests.
Interface: `exercise_queue(window,application,count,root,*,cycles=1,profile=False,
synthetic_cleanup=False)->dict`, no QApplication creation. Count choices fixed;
cycles1/2 only; refuse populated/nonisolated/nonanonymous state before mutation.
- [x] RED real window two-cycle output: analysed/enqueued/cancelled/restored/removed
  counts exact, zero final jobs/owners, worker high-water2, one confirmation/cycle,
  bounded per-stage measurements. Invalid/populated state refuses without changes.
- [x] Extract existing exercise/metrics, cancellation-only synthetic workers,
  explicit network/Keychain/deletion guards; benchmark delegates with cycles1.
- [x] GREEN shared tests and original benchmark/protocol/action tests.

### Task2: Opt-in frozen CLI and verifier

Files: `app.py`, `startup_check.py`, `scripts/check_packaged_app.py`,
`tests/test_startup_check.py`, `tests/test_packaged_app.py`.
Consumes Task1; CLI `--queue-items COUNT` only with startup-check; two cycles.
- [x] RED source CLI includes real queue evidence at allfour sizes while preserving
  synthetic preexisting preferences; never calls network/Keychain/deletion.
- [x] Connect after real window exposure, enable faulthandler for this mode only,
  keep normal startup/old isolated checks unchanged. Bounded operation deadline.
- [x] RED verifier wrong counts/booleans/empty cycles/missing stages/remaining
  tasks/source/offscreen/crash trace leakage; fake runner mirrors full real schema.
- [x] Implement strict report validation and safe native crash diagnostics; GREEN.

### Task3: Hosted integration and checkpoint

Files: workflow, FEATURE_BACKLOG, QUEUE_SCALE/CURRENT_ARCHITECTURE as appropriate.
- [x] Keep empty-window check and strict signature/archive probes; add actual frozen
  queue cases100/800/1000/5000 in hosted native job, each separate process.
- [x] Full Python/JS/drift/pipcheck, source diagnostic matrix; independent review
  and one Important/Critical RED→GREEN fix pass, full suite green.
- [ ] Audit allrefs/provider/exactindex/Public, inspect status/diff/index/protected
  refs; commit/push only after previous run terminal; verify remote and exact CI.

Ruling: autonomous incremental P0 diagnostic work, not visual redesign/Swift or
permission to publish/install. Cost if wrong: failed qualification must stay
visible; synthetic success cannot stand in for live-account/transfer acceptance.
