# One-shot UI and failed-callback retention

Mission B4 / Q11,A01: confirmed object-ownership defects, not a diagnosis of the
original800-video YouTube freeze and not proof of total process leak freedom.

## Causes and narrow changes

- `_inspection_ready` replaced/closed parented MediaDetailsDialog instances but
  never destroyed them. Their format tables, details and Apply closures retained
  older MediaItems. Tiny inspection probe retained5closed dialogs/items until
  the parent was deleted. The app now clears the matching owner on `finished`,
  schedules deletion and closes an active inspector during app shutdown. An old
  dialog cannot clear a newly installed owner; failed/stale Apply stays open.
- Queue/History context menus were one-shot parented objects with no disposal;
  callbacks captured selected jobs. A3-menu probe retained3menus/jobs. Their
  nested `exec` now has `finally: deleteLater()`, after action handling completes.
  Reusable UI menus/dialogs and ordinary QMessageBoxes were not indiscriminately
  changed; the latter did not reproduce this retention.
- TaskManager popped a stopped TaskRecord, then called `on_finished` before
  scheduling deletion and sending completion signals. A callback exception
  bypassed both. A3-task regression reproduced3thread children,3closure payloads
  and zero completion signals. Finalization now runs in `finally`; the callback
  exception still propagates through the existing Qt/Python error reporting.

## Tests and boundaries

New real-window tests cover five close/cancel/Apply/reset cycles, replacement,
shutdown, both context menus with dismiss and action execution, and captured
item/job weak references after deferred deletion. Original8cases allRED1.78s;
two added menu action cases preserve handler behavior. Stopped-task exception
regression separatelyRED0.25s. Combined lifecycle/media/restart57passed5.84s.
Native Cocoa lifecycle/media/task23passed4.96s; expanded native group201passed
50.17s/five existing test-only warnings. Independent review found no blocking
issue and independently ran11tests1.94s. Full isolated local suite:1,074passed
150.24s/five existing deprecation warnings/no skips. Exact-source hosted
qualification remains pending. JS10/no skips, protocol9fixtures and pipcheck passed.

The first corrected task test still saw one payload: PySide's error reporting
intentionally stores the most recent traceback in Python `sys.last_*` globals.
A fresh-process probe showed0threads/onepayload; releasing those debugger roots
showed0payloads with all3errors reported. The synthetic test now clears only its
reported-error debugger roots for the ownership assertion and restores pretest
state. Production error reporting/debug context is unchanged. This distinction
is not grounds to hide callback exceptions or weaken thread/completion assertions.

Deferred deletion requires event-loop processing. These checks are object/closure
ownership assertions, not RSS thresholds. Normal TaskManager completion did not
reproduce growing retention. Existing frozen diagnostic measurements intentionally
retain analysed/restored fixture lists after queue clearing and are not an empty
heap. Keep their persistence checks; use separate controlled ownership probes.
Torrent-console UUID marker pruning and broader progress-backlog/visible-History/
long-lived memory investigations remain separate unfinished work.
