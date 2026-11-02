# Persisted queue collections and scoped clearing

P0/Q06-Q07 continuation on qualified034efad/run41289264510. Existing queue
filtering and bounded removal/restart stay intact; no Swift or broad P1 redesign.

## Choice and scope

Use an explicit native collection selector with summary/progress/action menus over
the flat queue proxy. A tree rewrite would replace qualified selection/presentation
and a second item table would reintroduce per-job widgets. This is an engineering
choice under autonomous existing-project instructions, not design approval.

New admissions persist collection_id/name on DownloadJob (JSON payload defaults;
no SQL schema migration). Within an admission, partition known collections by
recorded original URL/title/type; distinct sources with identical titles do not
merge. Standalone items in that admission form a batch; torrents form one job/group.
Another admission gets distinct UUIDs. Metadata is allocated before the existing
atomic admission transaction and never published if it fails.

Old payloads remain readable. Legacy jobs with recorded collection title AND
original source derive a stable source/title/type key, labelled Legacy. Their
original import boundary is unknown and repeated historical imports may merge.
Other legacy jobs are explicitly Ungrouped. Never infer identity from title alone
or write a speculative migration into user data. Group labels reveal no auth paths.

## Presentation and ownership

Pure CollectionIndex stores immutable per-job projections and incremental status/
reported-progress aggregates. One-job progress updates are O(1); search/status/
collection filters do not reformat or rescan the source queue. A QAbstractListModel
adapts group rows to QComboBox; no per-job QObjects/new workers. Group changes and
full queue refresh synchronize; UUID selection memory remains safe. All queue
selection/Clear filters reset collection too.

Summary shows actual total/status categories. Average reported job progress is
equal-weighted, explicitly NOT byte-weighted or a success rate; completed jobs
count100, invalid/unknown progress is labelled unknown. Native transfer callbacks
update current aggregates. During a bulk operation show its actual bounded outcome
counts and explicitly defer the collection totals until final synchronization;
never display stale totals as current success. Group actions are disabled while
another batch owns admission; filters remain usable. Untrusted labels render plain
text, including modal scope descriptions. Compact900x650 controls must fit.

## Actions and safety

Pause/resume/cancel selected collection uses one explicit scope/count confirmation
and the existing32-ID QueueBatch status path. Cancel never downgrades Completed/
Completed-with-warnings (including completion after confirmation). No completed
media is redownloaded by these actions. Retry/auth behavior otherwise unchanged.

Clear menu: Completed(including warnings), Cancelled, Failed in current collection,
or all collections when All is chosen; Clear collection removes its entire scope.
These are not silently restricted by the per-job kind/status/search filters. Name
the scope and actual count in ONE confirmation. Keep queue-entry removal is default;
optional verified owned-file deletion uses the existing bounded service/Trash
rules. Freeze target UUIDs before modal event processing; recheck the batch lock
after confirmation; reread inventories after owner exit. Existing selected-job
removal shares the same execution path, not a duplicate implementation.

Deleted/unknown collection selection cannot broaden silently into All actions.
Zero targets, Cancel and failed admission/DB writes must not invent success or
touch unrelated jobs/files. Restart preserves collection identity. Legacy/new
groups survive DB reopen. No dedup/archive/batch-format/recovery completion claim.

## Qualification and constraints

TDD pure/randomized aggregates, real Qt roles/model/proxy, legacy/new persistence,
same-title groups, transfer membership, hidden selection,800/5000scoped actions,
one modal/keep default, stop/owner/failure races. Extend guarded frozen checks with
actual group controls/scoped keep-clearing while retaining all prior two-cycle/
18-stage/selection/restart/strict-archive evidence. Additional fixture work is not
a paired native speed improvement. Capture/inspect real compact/standard frames.

Same checkout/development branch; protect main/Swift/provider/October drafts.
No local Apple tools/admin, private cookies/accounts/media, release/upload/install.
Allrefs/reflogs/full-history/provider/exact-index scans and Public metadata before
every push; one fresh final read-only review and one blocking-finding TDD fix pass.
Full backlog and installation/licence/live/release gates remain open.
