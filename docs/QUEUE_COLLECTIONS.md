# Queue collections and scoped clearing

This P0/Q06–Q07 checkpoint adds native controls over the existing flat queue;
it is not an approved P1 redesign, deduplication, download archive or complete
freeze/leak qualification. No Swift/backend protocol change is made.

## Identity and compatibility

`DownloadJob.collection_id` and `collection_name` are optional JSON fields, not
new SQLite columns. `assign_collections` allocates a fresh import UUID per
recorded original-URL/title/type partition in each admission. Identical titles
from different sources stay separate. Re-importing the same source creates a
new collection. Standalone items in one admission form a batch; a torrent forms
one job/collection. Admission persists everything before publishing runnable jobs.

Old payloads load with empty defaults. Jobs that retain both original URL and
collection title derive a stable `legacy:` key, labelled Legacy. Their original
import boundaries cannot be recovered; historical repeat imports may merge.
Other old jobs are explicitly Ungrouped. Title alone never implies identity.
No speculative user-database migration is performed. Restart and transfer
callbacks preserve the captured collection, including its name.

## Native presentation and progress

`queue_collections.CollectionIndex` caches immutable status/progress projections;
one job change adjusts one group and the global aggregate, without rescanning N
jobs. `collection_model.CollectionListModel` exposes groups to a native combo;
`collection_controls.CollectionControls` owns presentation/signals only. The queue
proxy combines collection with existing kind/status/literal-search roles. No
per-job widget, worker, SQL or network request is added for aggregate presentation.

The bar explicitly shows **equal-weighted reported job progress**, not bytes or
a success rate. Completed (including warnings) counts100; invalid/nonfinite
progress is unknown and excluded from the known-value mean. If ANY values are
unknown the bar is hidden; explicit completed/total and known/total/unknown counts
replace it. When all values are known the bar says Avg. item; its tooltip explains
equal weighting/the denominator/not bytes/not success. During a batch, actual operation completed/failed/pending
counts replace the stale aggregate and say that totals refresh afterward.
Collection choices/totals synchronize at batch completion, not on every32-ID
slice. Normal transfer callbacks update incrementally. Filter changes do not
resynchronize the collection index; changing kind still reformats queue columns.

## Actions and safety

Choose a collection to Pause, Resume or Cancel it with one count/scope confirmation
and the existing32-ID QueueBatch executor. Completed/Completed-with-warnings jobs
remain completed even if they finish while confirmation is open or while their
actual owner exits. Every slice rechecks collection membership. Ordinary selected
pause/cancellation has the same completion protection.

The visible **Clear Completed** primary face clears completed entries (including
warnings); its arrow offers Completed, Cancelled and Failed, plus
the entire current collection. With All collections selected, status clearing
addresses the **entire queue**. These explicit scope actions intentionally ignore
per-job kind/status/search filters; the one confirmation names the actual scope
and count. Queue-entry removal keeping files is the safe default. Optional
verified owned-file deletion retains existing owner-drain/32-snapshot/one-worker
and file-ownership/Trash boundaries; no destination wildcard deletion.

ALL scoped clears, even one item, use the transactional bounded executor, rather
than per-item small-clear deletion. Deferred-owner failures settle truthfully and
retain entries. Targets are frozen UUIDs before the modal. Status/group eligibility is checked
again afterward, before each admitted slice and after owners stop before file
cleanup. A job that no longer matches is retained with truthful skipped/failure
reporting, rather than deleting newly completed/other-collection work. Generic
selected-job removal deliberately remains unrestricted by status. An open menu
captures its collection; deletion/fallback cannot broaden that action into All.
Clear filters/Select all reset the collection too; hidden selection never supplies
action targets. Unknown/deleted collections are refused.

## Evidence and remaining QA

Before this checkpoint, exact034efad/run41289264510 passed Linux841, macOS60
backend tests, Swift25/actual workers, protocol9, the frozen four-size/two-cycle
matrix, replacement and strict extracted-archive launch. That qualification is
not evidence for the newer collection checkpoint.

Connected new/old tests:135passed56.41s. The pre-diagnostic full local suite:
870passed88.80s. Native probe/packaged verifier tests:76passed4.23s, including
18 observed RED→GREEN missing/misleading group-report cases and a broken real
clear control that the old probe failed to detect. Final pre-review full local
suite:889passed119.48s, no skips/warnings reported. Extension10/protocol9 and
pip dependency check pass.

The single fresh review found five Important issues: Pause downgraded completed
jobs while owners exited; group actions failed to recheck membership; small
clears could partially commit and leave stale UI; mixed unknown progress could
show100%; escaped malformed legacy Unicode could abort hashing. Each was observed
RED→GREEN, including real TaskManager owners and SQLite trigger/reopen tests.
Valid legacy hashes remain unchanged. Connected66passed12.22s; full post-fix
900passed121.98s. The further native-gate extension now requires the actual
primary Clear Completed control and rejects a disconnected button/false evidence;
native probe/verifier78passed5.19s. Exact hosted qualification is still required.
Final full local suite including those primary gates:902passed124.31s, no skips
or warnings reported. Extension10/protocol9/pipcheck/shellsyntax pass.
Minor deferred: name-only changes retain the aggregate's first label until its
group is removed; no user rename feature is claimed.

The guarded source matrix adds a **separate** second N-job admission after the
original nine stages; all prior18records/two cycles, selection/restart, worker,
SQL/persistence and strict-archive gates remain. Same-title different-source
groups exercise real selectors/menus, protected completion, three actions/four
keep-clears, other-group preservation and independent committed SQLite reads.
One incremental update emits two summary-row notifications with zero full index
syncs. Extra fixture work is not a paired performance improvement:

| Items | Extra collection sequence wall | CPU | Maximum heartbeat gap |
| ---: | ---: | ---: | ---: |
| 100 | 0.194s | 0.181s | 0.028s |
| 800 | 1.445s | 1.357s | 0.241s |
| 1,000 | 1.820s | 1.711s | 0.309s |
| 5,000 | 9.840s | 9.313s | 1.652s |

The post-review rerun also passed all four sizes, with primary Clear Completed
and zero final owners. Extra sequence wall/gap:100=.208/.029s,800=1.489/.244s,
1000=1.850/.309s,5000=10.087/1.670s. Early cases shared brief probe-test load;
neither run is a calibrated/paired speed improvement.

These are single local offscreen Python3.12.13/PySide6 6.11.2 observations, not
Cocoa latency acceptance or leak evidence. The5,000 gap remains material. Modal
choices are intercepted, not human click time. No personal accounts, network,
real media transfers or deletions occur. Source benchmark command:

```sh
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B \
  scripts/benchmark_queue.py --items 100 800 1000 5000
```

Real offscreen widget frames were captured/inspected at actual900x650 and1180x820,
plus the clear menu, in the ignored plan evidence workspace
`.superpowers/sdd/2026-11-01-queue-collections/collections-*.png`.
New controls fit; the compact queue viewport remains only113px high, with narrow
title/destination cells and an oversized details area. The standard collection
label/control gap also needs the future approved layout work. No professional
design, native fullscreen/light-dark, accessibility or packaged visual acceptance
is claimed. The reported incident is now explicitly a window-stayed-open freeze,
not a confirmed native crash. Live conditions still need user participation.

Keep all remaining requirements in FEATURE_BACKLOG.md, including dedup/archive,
batch settings, recovery/memory/playlist work, the actual Media Viewer, site-scoped
auth/privacy/onboarding and controlled updates/releases. No release/upload/install
or local Apple build tools are authorized by this checkpoint.
