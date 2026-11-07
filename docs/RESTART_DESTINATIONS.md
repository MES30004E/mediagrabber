# Stable restart destinations

Scope: mission B2 / Q05. Repeated explicit restart previously appended a fresh
`restart-UUID` beneath the **previous attempt**, growing the path on every retry.
The existing test restarted the original job twice, so did not catch the saved
job → restart → save/reload → restart sequence.

## Non-destructive strategy

- `DownloadJob.restart_base_directory` is an optional persisted JSON field. First
  restart captures the canonical current destination; subsequent attempts use
  fresh unique siblings there, not the preceding attempt. DownloadOptions and
  the SQL schema are unchanged.
- Legacy jobs without the field use their current saved destination as the new
  anchor, even if it is already nested or named `restart-*`. Never infer an older
  root, rename/move old folders, reuse a previous attempt or clean unknown files.
- Before filesystem effects, `queue_restart._restart_base_directory` validates
  a nonempty saved anchor and its current attempt/created-directory relationship.
  Inconsistent metadata, relative anchors and changed attempt symlinks fail closed.
  The error remains in the existing Interrupted/failure accounting path.
- The anchor is **not ownership**. `delete_restart_state` still receives the current
  attempt's `options.download_dir`. Only after cleanup is its new sibling assigned.
  `created_job_directory` continues to mean the individual attempt, never the
  shared anchor. Clear cannot use this new field to delete previous attempts.
- Keep retains every old final, partial, temporary, subtitle and thumbnail file.
  Replace retains its existing explicit current-inventory-only policy. Missing
  inventories cannot cause reuse of unreported partials because the next folder
  is fresh. No cleanup/migration of historical restart directories is attempted.
- Authentication, formatting, torrent file selection, collection identity, job
  UUID, owner draining, one confirmation, 32-job worker slices and durable
  Interrupted-before-cleanup/Waiting-after-commit sequencing are preserved.

Future queued-destination editing must explicitly reset/validate restart metadata;
silently changing only the current destination is deliberately rejected. No such
editor exists in this checkpoint. This is not a claim of atomic filesystem safety
against adversarial concurrent symlink replacement in the older ownership helper.

## Evidence

- New policy tests first failed: **23 failed in0.38s**, reproducing the nesting
  and missing validation. After correction, policy/ownership/controller tests:
  **56 passed in0.72s**.
- Real-window repeated Keep/Replace actions use the actual counted modal, then
  reconstruct live jobs from SQLite before restarting again: two tests passed.
- Native Cocoa policy and restart UI suite: **39 passed in13.86s**, including
  existing800/5000-job bounded controller, cancellation and shutdown checks.
- Independent read-only review found no blocker; independently23passed0.28s.
- Full isolated local suite: **1,055 passed, five existing test-only deprecation
  warnings in204.60s**, no skips. JavaScript10passed/no skips, protocol9 fixtures
  matched, pip check found no broken requirements. Full command:
  `QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m pytest -q -p no:cacheprovider`
  with temporary MORGAN_DATA_DIR/MORGAN_LOG_DIR/MORGAN_CACHE_DIR.
- Hosted native coverage now includes scheduler-capacity, destination and restart
  UI tests. Exact-source hosted results must be recorded before
  declaring this checkpoint qualified. No real user files or transfers tested.

Commands: `QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m pytest -q
tests/test_restart_destinations.py tests/test_queue_restart.py tests/test_file_ownership.py`
and `QT_QPA_PLATFORM=cocoa .venv/bin/python -B -m pytest -q -p no:cacheprovider
tests/test_restart_destinations.py tests/test_queue_restart_ui.py`.
