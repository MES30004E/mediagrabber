# Atomic Queue Admission Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline with TDD; preserve the running hosted qualification and existing checkout.

**Goal:** Provide atomic batch persistence and prevent runnable phantom jobs after failed admission, as a prerequisite to bounded asynchronous queue services.

**Architecture:** Keep schema and existing database lock. Single-item APIs delegate to Iterable batch APIs using one transaction and lazy row serialization. Media admission publishes its new jobs only after persistence succeeds. This does not implement the later asynchronous batch controller or model/view migration.

**Spec:** FEATURE_BACKLOG Q01/Q09/Q11 and architecture debt register; measured per-item transaction baseline in QUEUE_SCALE.md.

## Constraints

No personal data, local Apple tools, installation, release, main/Swift/provider changes or conflicting push during hosted run40993057336. Preserve unrelated drafts. Failures must roll back before visible admission. Empty batches must do no SQL. Database format remains compatible.

## Tasks and evidence

1. Add generator-compatible `Database.save_jobs(Iterable[DownloadJob])` and `remove_jobs(Iterable[str])`; preserve save_job/remove_job. Tests:800records one commit, real SQL trigger mid-batch abort preserves old row/status, serialization failure rolls back and retry succeeds, empty iterable causes no transaction. Four initial tests observed RED then GREEN.
2. Connect real `_enqueue_payload`: one atomic media admission, persistence before publication for media/torrent. Tests observed RED800commits and REDphantom runnable job on failure, then GREEN. Run full Python/JS/drift and actual benchmark; don't infer broader scale acceptance.
3. Read-only checkpoint review; fix Important/Critical via RED→GREEN, commit coherent source/tests/docs locally. No push over the live native job. Retain async batch actions, bounded widgets/transaction slicing and fault recovery as next P0 work, not completed by this step.

## Review focus

Mid-generator/serialization/SQL failures must not leave partial rows. Empty iterators cause no SQL. Existing one-job behavior/restart/schema must stay intact. Admission DB failure cannot expose runnable entries. UI execution and transaction size remain synchronous/unbounded by this API and must not be advertised as the finished scalable controller.
