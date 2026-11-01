# Bounded explicit bulk restart

Continue P0/Q05 from qualified72fd947/run41210675065. Restart currently loops
through per-job modal decisions, filesystem cleanup and SQLite commits on the GUI
thread. This is a measured-path candidate for hangs, not the unique proven cause
of the user's frozen window.

Choose the existing QueueBatch/TaskManager pattern, with a focused restart
controller owning at most32 admitted snapshots and one worker. A GUI-only sliced
loop still blocks on filesystem operations; a worker per job is unbounded. This
is an engineering choice under the autonomous existing-project instructions,
not permission for a redesign or real user-file cleanup during validation.

One dialog snapshots selected UUIDs and shows actual active/completed counts.
Default Keep outputs deletes recorded partial/temporary state while retaining
final/subtitle/thumbnail outputs, including legacy overlapping aliases. Every
restart uses a unique child destination: cancellation suppresses a worker's final
result, so its last file inventory may be incomplete. Never silently reuse an
unrecorded partial. This also
works for torrent fixed relative paths, unlike merely changing a media template.
Replace explicitly permits permanent deletion of recorded in-root final paths
but still uses a fresh destination. Never scan
the destination or delete unrelated files. No GUI existence checks are needed.
Re-read current inventories after active owners stop, not before the modal dialog.

Persist admitted jobs as Interrupted BEFORE any cleanup. Only after cleanup and
the stopped cleanup thread may the GUI atomically save/publish Waiting snapshots.
Failure retains an Interrupted entry and truthful partial-cleanup warning; a failed
final save leaves the durable prepared state non-runnable. Preserve auth, route,
media/torrent options and UUIDs. Pending removal wins; no cleanup while a transfer
owner remains. Other actions/dispatch are blocked by the existing batch lock.

Stop finishes the admitted slice and stops future admission, with accurate counts.
Shutdown cancels the worker, retains uncertainty evidence, drains ownership and
never publishes Waiting after closure. No DB schema or downloader rewrite.

Tests: owned temporary files only; keep/replace/missing/outside-root/failure;
32-bound/deepcopy/thread-exit/redaction;800/5000jobs/one dialog/heartbeats;
late owner inventory, stop/admission/prepare/final-commit/close failures; real
history invalidation. Extend both frozen diagnostic cycles with independently
checked restart evidence and keep all prior selection/18-stage/archive gates.
Additional fixture work prevents direct comparison of native timings to prior runs.

Same checkout/development branch. Protect main/Swift/provider/October drafts.
No local Apple tools/admin, live accounts/media, release/upload/install. Before
every push scan all refs/reflogs/full history, provider and exact index; triage
findings and verify Public metadata. One final independent read-only review only.
The full feature backlog, installation decision and live/release gates remain open.
