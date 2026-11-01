# Explicit bounded bulk restart

Restart from Beginning now confirms the selected UUIDs once, shows active and
completed counts, and defaults to Keep existing outputs. Cancel changes nothing.
The dialog is metadata-only: no destination scanning or per-job existence checks
block its GUI. It rechecks the batch lock after the modal event loop; removal does
the same, preventing stale confirmations from interleaving with an admitted batch.

## Safety and behavior

- One QueueBatch admission stream, up to32 snapshots and one owned cleanup worker
  per slice. Selected active owners must stop before their latest inventory is read.
- GUI persists Interrupted preparation before any filesystem changes. Worker
  snapshots never mutate live jobs/Qt/database. After the cleanup thread stops,
  GUI atomically saves and publishes successful Waiting jobs; failures remain
  Interrupted with a partial-cleanup warning. A failed final commit leaves the
  durable prepared state non-runnable, not an automatically dispatchable job.
- Every restarted job gets a unique `restart-<UUID>` child destination. Cancellation
  suppresses a worker's final result, so its last file inventory can be incomplete.
  A fresh destination prevents silently resuming an unreported partial and protects
  fixed torrent filenames. The media template, auth, route and torrent selections
  are retained. Repeated restarts currently create nested child destinations.
- Keep retains ALL old files, including recorded partial/temporary paths. A stale
  temporary path may have become final after cancellation. The fresh destination
  provides from-beginning behavior without risking deletion of that output. Old
  partials consume disk space and require explicit review/removal.
  Replace explicitly permits permanent deletion of recorded in-root old outputs;
  it still downloads into a fresh child folder. No wildcard/destination scan or
  unknown/foreign-file deletion. Retained older outputs stay on disk but are no
  longer the restarted job's active inventory; new-job removal cannot delete them.
- Before any cleanup, reject absolute/parent-traversing filename templates or
  torrent relative paths and missing destinations. Invalid jobs remain Interrupted
  with a corrective error, not silently rewritten or dispatched outside the child.
- Stop finishes the admitted slice (up to32), then stops future admission. It does
  not promise immediate rollback of filesystem effects. Completion/failure/pending
  counts remain visible. Other queue actions and dispatch use the existing lock.
- Shutdown cancels the cleanup worker, suppresses late Waiting publication,
  persists uncertainty and drains ownership even if uncertainty/active-owner DB
  or settings persistence fails. Retain the running marker on those failures.
  Pending removal takes precedence over restart. No application schema migration.

## Regression and diagnostic evidence

Real temporary-file tests cover keep/replace/sidecar aliases, foreign/missing and
unreported paths. Controller/UI tests exercise worker snapshots/thread exit,
late transfer inventory,800/5000selected jobs, one dialog/default/cancel, Stop,
prepare/final/admission/result failures, history invalidation, modal re-entry and
shutdown/persistence failure. The single independent review found three blocking
safety cases: escaping templates, late temporary→final promotion, and active-owner
persistence failures bypassing shutdown.13 regressions observed RED, then GREEN;
Keep now retains every old file and close always reaches worker drain despite
settings/DB failures. Full local841passed82.04s; extension10/protocol9,
pip check clean (only local pip cache permission warning).

The source/frozen queue diagnostic additionally restarts each complete batch in
both cycles before transfer workers. Empty-inventory cleanup is guarded: no real
paths are touched. Independent read-only SQLite checks verify each32-ID prepared
commit; final payloads/status/counts must match. Require one restart confirmation,
one worker, max32slice, zero GUI cleanup/errors and exactly2N writes/2ceil(N/32)
commits. All prior18stage records and selection/worker/archive gates remain.
Additional fixture work prevents direct timing comparison with older native runs.
New exact hosted qualification is still required after audited publication.

Paired source callback probe executes the qualified72fd947 restart methods versus
the new controller in the same current-window fixture, fresh process per case,
already populated/rendered, with1ms synthetic per-job work and intercepted
confirmation decisions (no human click delay). It measures responsiveness, not
actual media/storage throughput. Sequential observations (not hard budgets):

| Jobs | Longest GUI gap before→after (s) | Total wall before→after (s) | Commits before→after |
| ---: | ---: | ---: | ---: |
|100|0.1518→0.0131|0.1518→0.1899|100→8|
|800|1.2493→0.0644|1.2493→1.6380|800→50|
|1000|1.7775→0.1195|1.7775→2.1549|1000→64|
|5000|8.3721→0.3826|8.3721→10.5737|5000→314|

Confirmations N→1 and GUI cleanup calls N→0 in every case; all jobs committed
Waiting and final owned tasks0. The additional durable preparation doubles rows
written (N→2N), while transactions are bounded/batched. Total wall time and peak
RSS are NOT improved:5,000peak220.03→244.80MiB. The goal here is responsive and
failure-safe restart, not a faster storage device or proof of leak freedom.
All four final pairs were repeated after the review fixes, without another test
suite workload. Keep performs no actual filesystem deletion; its injected1ms is
controlled worker work, not a claim about physical disk speed.

Actual offscreen Light dialog with800jobs/2active/3completed was captured and
inspected,699x225inside900x650parent. Counts, safe default, irreversible Replace
wording, fresh destination and Stop semantics fit. Evidence remains in the local
ignored plan workspace; this is not Cocoa/dark/fullscreen/P1-design acceptance.

No personal account, media transfer, user-file deletion, installation, release,
asset upload or local Apple build tooling was used. Collections/dedup/relaunch,
long-run memory/freezes, real file/volume races and explicit live QA remain open.
