# Synthetic queue scale baseline — 30 October 2026

This records reproduction, narrow stall/removal fixes and remaining scale gaps,
**not complete crash/scale acceptance**. The diagnostic itself does not change
application behavior; the production corrections below do. The native crash
reported by real QA has not yet been reproduced/classified. No personal playlist,
cookies, network download, media output or normal application state was used.

## Reproduce

From the repository root, with its repaired Python 3.12 environment:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  scripts/benchmark_queue.py --items 100 800 1000 5000
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  scripts/benchmark_queue.py --items 100 --profile
```

The probe runs each size in a separate child with faulthandler enabled and a
120-second limit. It builds the real offscreen PySide6 MainWindow using synthetic
flat analysis items, real queue/persistence/actions and two bounded synthetic
download workers. It drives analyse/enqueue/start/progress/pause/resume/cancel/
reload/remove, counts SQL commits/writes and intercepted confirmation requests,
and records CPU, process peak RSS, sampled native threads, active tasks and
heartbeat gaps. Workers wait for cancellation; no transfer or retry storm is
simulated. Real modal choices are intercepted as **keep files**; 800 actual dialogs
are never shown. Successful operation assertions are not a latency pass.

Only test-owned temporary data/log/cache/download paths are used. All window
timers are stopped before processing events; real socket/Keychain operations fail
the probe. It does not call local Xcode/signing tools. On this Mac the execution
sandbox forbids `ps`; permission was granted for read-only **own-process** native
thread counting. Without that access the probe reports an error, not a fabricated
thread count. The first invocation without `PYTHONPATH=src` failed imports; that
was a harness launch error, not an application crash.

## Observed baseline

Measured on the local Mac, Python 3.12.13/PySide6 6.11.2, queue behavior from
`049c44d` (the following Canvas-only packaging fix does not change queue code).
State lives in a fresh temporary directory, not the external preferred app
installation. Measurements are single runs, not a calibrated performance budget.

| Items | Enqueue wall | Pause-all wall | Resume-all wall | Cancel-selected wall | Removal wall | Confirmation requests | Peak RSS observed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 0.046 s | 0.248 s | 0.245 s | 0.246 s | 0.023 s | 100 | 133.25 MiB |
| 800 | 0.246 s | 14.812 s | 14.791 s | 15.268 s | 0.099 s | 800 | 167.33 MiB |
| 1,000 | 0.293 s | 23.415 s | 23.353 s | 24.118 s | 0.123 s | 1,000 | 175.66 MiB |
| 5,000 | Not completed | Not completed | Not completed | Not completed | Not completed | Not established | 120 s child timeout; no final sample |

The completed cases restored all cancelled jobs from SQLite and removed all queue
entries under the intercepted keep decision. Actual active tasks remained at most
2; sampled native threads at most 10. Every enqueue/pause/resume/cancel/remove
operation committed once per affected item: 800 commits each at 800 items. The
queue held 800/1,000 QProgressBar children, respectively. Peak RSS is the process
high-water mark, not current RSS or proof against retention/leaks. Sampling does
not prove a hard thread ceiling. Offscreen render timing is not Cocoa visual QA.

Heartbeat gaps tracked the long synchronous calls: about 14.8–15.3 seconds at 800
and 23.4–24.1 seconds at 1,000. The event loop is not acceptably interactive there.
No exception/native fault occurred in the first three cases. The 5,000-item
timeout is not evidence of OOM or a native crash; its first run did not emit
intermediate samples. The probe now retains bounded stage samples in stderr on
timeouts to identify the next stalled boundary.

## Profile evidence, not a guessed crash cause

An independent 100-item `--profile` run measured pause-all at 0.252 s. Its cumulative
profile attributed 0.237 s to `_refresh_queue`, including 0.235 s in 800
`QTableWidgetItem.setText` calls; serialization/asdict was about 0.007 s. This
locates the dominant measured stall in full-table updates, rather than assuming
SQLite, worker count or private networking caused the reported crash.

Inspection shows QHeaderView ResizeToContents and every-cell writes during queue
refresh, full history recreation per progress event, and per-row progress widgets.
Investigate header/model notification costs and native object lifetime before
choosing a fix. A QTableView/model/delegate would avoid per-cell widgets; batching
must preserve stable selection/job IDs and only mutate models on the GUI thread.
The official [QAbstractItemModel reference](https://doc.qt.io/qtforpython-6/PySide6/QtCore/QAbstractItemModel.html),
retrieved 30 October 2026, requires model API calls on the owning GUI thread and
queued updates from workers, and documents begin/end insert/remove plus
dataChanged for incremental updates. The attempted old model/view overview URL
returned404 and supplied no evidence.

## Next P0 checkpoint

- One selected-job snapshot, one counted confirmation, **keep files** default and
  one explicit optional owned-file deletion decision. No per-job modal loop.
- Bounded asynchronous batch execution/cancellation with completed/failed/pending
  counts; defer active removal until its owned task stops; preserve real outputs.
- Reproduce refresh/header bottleneck separately, then replace/coalesce the
  measured expensive path with regression tests and rerun the identical matrix.
- Batch DB transactions and bounded progress/metadata/thumbnail admission;
  collection/selection/dedup/restart acceptance remains in FEATURE_BACKLOG.md.
- Capture native/exception traces if reproduced; active download races, repeated
  cycles, real Cocoa and packaged application still need separate qualification.

## Narrow production correction and after measurements

Nonstretch queue columns now use Interactive sizing; one explicit content-size
pass happens only after structural changes. This preserves ordinary manual
column resizing without repeated every-row measurement on each status-cell edit.
One selected-ID snapshot now obtains one keep/delete/cancel dialog (keep files is
the default); active jobs still defer removal until their owned task finishes.
After the modal dialog, current job objects/inventories are resolved by ID because
worker results can replace them while the dialog processes events.

The independent single-variable diagnostic changed header sizing only during
800-item pause: 14.812s became0.120s including profiler, while untouched resume
and cancel remained15.773/19.149s. That supports the stall mechanism without
attributing an unreproduced native crash to it.

The identical four-size CLI after the production correction reported:

| Items | Enqueue wall | Pause-all wall | Resume-all wall | Cancel-selected wall | Removal wall | Confirmation requests | Peak RSS observed |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 0.038s | 0.016s | 0.016s | 0.008s | 0.009s | 1 | 136.56MiB |
| 800 | 0.227s | 0.065s | 0.071s | 0.067s | 0.063s | 1 | 177.72MiB |
| 1,000 | 0.299s | 0.085s | 0.102s | 0.104s | 0.083s | 1 | 182.28MiB |
| 5,000 | 1.247s | 0.388s | 0.422s | 0.400s | 0.399s | 1 | 407.22MiB |

All four restored cancelled state and emptied the queue after keep-files removal;
active tasks at most2 and sampled native threads at most10. The 800-item measured
max operation heartbeat gap was0.234s during enqueue;5,000 still reached1.302s.
Per-item DB commits and N progress widgets remain; the higher measured RSS is not
a memory optimization. This does **not** deliver asynchronous collection actions,
bounded widget memory, a model/view architecture, leak qualification or realistic
active transfer/race/native crash validation. Those remain release-blocking QA.

There are **no new-design screenshots yet**. The new
`test_queue_scale_probe.py` verifies the diagnostic really drives real queue and
persisted operations, but deliberately does not bless the baseline confirmation
count, widget-based implementation or latency as correct behavior.

## Atomic admission prerequisite

The subsequent persistence checkpoint adds iterable `save_jobs`/`remove_jobs`
transaction APIs without a schema change. Media admission saves its complete
batch before publishing runnable entries; torrent admission also saves first.
Serialization or SQL failure rolls back the batch and cannot publish phantom jobs.
Single-job callers retain their existing APIs. Empty batches do no SQL.

A new real synthetic probe measured800-item enqueue at0.149s/one commit (previous
0.227s/800commits) and5,000-item enqueue at1.098s/one commit (previous1.247s/
5,000commits). Both sizes completed the probe with one removal confirmation.
These are single-run timings, not a memory improvement or broad responsiveness
qualification; the5,000 enqueue heartbeat gap was still1.165s. Other actions still
have per-item writes. The API consumes rows lazily but does not impose a maximum
call size or yield the GUI thread. A bounded asynchronous service must choose its
chunk sizes, handle errors and coordinate dispatch/shutdown; this remains next P0
work, alongside model/view and bounded widget/progress memory.

## Bounded status actions

Large (>32) pause/resume/cancel now use one GUI-owned timer controller,32 stable
IDs per event turn. It copies current jobs and commits a slice before publishing
state or cancelling active workers. One action is admitted at a time; dispatch
waits. Stop batch action leaves unprocessed jobs unchanged; shutdown stops future
slices. Completed/failed/unchanged/pending counts and bounded redacted errors are
reported. Small actions remain immediate. This creates no per-job worker threads.

The benchmark now waits for asynchronous completion while processing Qt events.
800-item pause/resume/cancel total times were0.193/0.109/0.213s, with maximum
heartbeat gaps0.091/0.047/0.097s and25transactions each. At5,000: total times
1.554/0.949/0.838s, heartbeat gaps0.345/0.432/0.331s and157transactions each.
These are single local offscreen measurements. Total time increased relative to
the synchronous narrow fix; the measured improvement is event-loop yielding and
transaction count. Full table/history refresh and row widgets still impose costs.
Enqueue, removal, restart and file IO are not made asynchronous by this controller;
native crash/real-transfer/memory/visual qualification remains incomplete.

Conflicting restart/remove/clear/seeding actions are refused while a status batch
is pending; they cannot destructively reset a job that a later slice will mutate.
Progress-signal cancellation is idempotent, including a listener starting a new
batch. Regressions reproduced both conflict and duplicate-completion defects
before their fixes. The independent review initially stopped at an account usage
limit, then resumed after reset and cleared the narrow checkpoint with no
outstanding Critical/Important finding. It independently verified closing after
a committed32-job slice prevents further writes while768 remain pending. Retaining
that shutdown scenario as a persistent regression is a deferred coverage minor.
Native/hosted validation for this controller remains separate; the older green
archive run is not a substitute.

## Bounded keep-files removal

Large keep-files removal now uses32-ID atomic delete slices, one confirmation,
and no file-deletion helper. Active tasks are requested to stop; entries remain
visible/pending until the owned completion callback deletes the queue record.
BatchOutcome tracks applied, failed, unchanged and correlated waiting IDs. Unknown
or repeated completion IDs cannot change totals. Stop prevents future slices but
admitted removals still finish; close retains unresolved entries rather than
resuming removal after a restart. Small/explicit file-deletion actions retain
existing behavior; optional filesystem deletion is **not yet asynchronous**.

The actual800/5000 synthetic keep-removal probe passed with one confirmation,
25/157 transactions, wall0.017/0.111s and maximum heartbeat0.015/0.081s. A separate
real TaskManager test drains two synthetic owned threads before reporting800
completed. These are local offscreen measurements, not proof of native crash
resolution or memory stability; process peak RSS in the5000 run remained~412MiB.

Review found two Important lifecycle/counting defects: pending restart could run
its deletion helper before a newer keep-files removal, and an OSError with no
message could report success despite retaining an entry. Both reproductions
failed before fixes and pass now. Removal supersedes pending restart, failed
stopped entries recover as Interrupted, and exception-type fallback keeps failure
counts truthful. Full Python suite631passed20.12s, JS10/protocol9 matched.

Deferred minor: while admitted workers remain pending, Stop changes internal
cancel state without immediately emitting another progress notification. Counts
remain pending, not successful; final worker settlement updates the UI. Immediate
stopped/waiting feedback should be refined with the remaining batch UX.
