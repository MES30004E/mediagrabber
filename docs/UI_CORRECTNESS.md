# UI correctness — Checkpoint A in progress

This is a conservative repair checkpoint, not the later professional redesign,
rebrand or Library/playback acceptance. Published collection rollback:
`9ed1082fbdace1bc5fea7a6943666c759881a80d`, hosted run `41385802502`.

## Theme component

`theme.apply_theme` retains its public interface. One application-owned
`_ThemeState` recomputes Qt stylesheet palette roles when the theme or actual
System palette changes. Previously the unchanged stylesheet string prevented
existing sidebar/table/dialog colors from updating. A native scheme notification
can arrive before the new palette; observing `QApplication.paletteChanged` also
updates hidden controls without freezing System appearance into a manual palette.
Native `QStyleHints.setColorScheme` is capability-guarded for the declared Qt6.7
floor; the local fallback test is not execution on an actual Qt6.7 installation.

`NavigationShell` retains the standard download arrow shape, supplying readable
normal/selected/disabled colors. The original application icon is unchanged.
Two `StatusLabel` consumers retain connection/provider state, messages and
tooltips while updating semantic colors. Custom System palettes get a neutral
contrast fallback where necessary. Ordinary captions/header text use WindowText,
not translucent placeholder text. Native System disabled button text required an
opaque stylesheet color; the native application palette itself remains untouched.

No per-job theme objects, workers, timers, disk/network operations or preferences
writes were added. Unchanged theme applications do not repolish the widget tree.

## Actual native evidence and limits

Synthetic source Cocoa captures cover Download, Queue, History and Settings in
Light/Dark/System at requested900×650/1180×820/1440×900 and Queue fullscreen,
plus roundtrips, a details dialog and popup. The theme-component audit records45 captures,
zero external I/O attempts and zero final task owners. Actual larger normal
windows were OS-clamped to1440×816; fullscreen1470×923 at DPR2. These are not
claims of arbitrary-display or packaged-app acceptance.

Before/after frames were inspected for stale sidebar/table colors, unreadable
text, arrow, status, menus, details and restored Light/System appearance. Theme
switch timing is recorded in the ignored plan workspace; it does not establish
large-queue responsiveness or memory qualification. Test-owned windows must be
destroyed after accepted close and drained workers: close alone retains their
parented C++ widgets and makes repeated global stylesheet checks unrepresentative.
The test teardown never destroys a live or pre-existing/global window.

Native keyboard regression uses explicit Qt synthetic active-window context and
checks retained logical focus/UUID selection and actual shortcut delivery. macOS
may refuse foreground activation before any theme operation; this does not test
hardware-keyboard focus or grant permission to control another application.

## Still unfinished

- Native progress repair is locally tested below; exact hosted frozen validation
  remains outstanding with the rest of Checkpoint A.
- Layout/preferences and discoverable actions are locally tested below; final
  whole-checkpoint visual/performance/hosted acceptance remains outstanding.
- Concise counted confirmation dialogs and expandable technical details are
  implemented and locally tested below; hosted qualification remains pending.
- Final review fixes, updated full-suite evidence and exact-commit hosted
  packaged/macOS/Linux qualification.
- Full B/C/D/E roadmap in FEATURE_BACKLOG, including actual Library playback,
  authentication acceptance, remaining stalls/retention, rebrand and releases.

No local build, release, upload, installation, protected-branch or Swift work is
part of this component. Local source/native tests are not a publication approval.

## Theme verification result

- Full Python suite: **931 passed, 3 warnings in143.06s**; no skipped tests.
- Focused theme/UI/Settings: **44 passed in13.48s**.
- Actual Cocoa theme consumers: **18 passed in15.94s**, including late/custom
  System palettes, real menu/header/disabled pixels, focus/UUIDs and shortcuts.
- Companion JavaScript: **10 passed,0 failed,0 skipped**; protocol9 shared
  fixtures match; pip check and packaging-script syntax check passed. No build.
- The three warnings are the documented deprecated, test-only Qt active-window
  API used for synthetic keyboard context; no production deprecation added.

The first completed full run returned930passes/one failure: an older test
incorrectly expected the early scheme signal to reset the palette immediately.
It now verifies Qt's documented two-stage timing and actual table recoloring.
Two older fixture-accumulation runs were terminated, not counted as passes.
Test teardown now also delivers already-scheduled DeferredDelete events.
This qualification is local source/theme-only; whole-A hosted evidence is pending.

## Native progress component

Actual Cocoa QWidget painting reproduced5066pixels entirely outside a literal
offset progress cell. A bare-QImage probe produced native graphics-context errors
and was rejected as evidence. The isolated renderer fix saves/intersects the
painter clip, translates the native track to local coordinates, and restores the
entire painter state. It retains existing model/UUID/progress roles and no row
widgets. Unknown progress keeps the normal text delegate.

Percentage text is now explicitly drawn beside the track (mirrored for RTL).
This is necessary because [Qt documents that QMacStyle ignores progress text](https://doc.qt.io/qt-6/qprogressbar.html#textVisible-prop).
It is not a new progress estimate or a change to extractor/transfer data.
Actual known0/25/100, unknown, RTL, selected/disabled states, clip/transform and
DisplayRole text are exercised through QWidget paint/grab, not just model values.

The shared source/frozen diagnostic now compares actual two-row viewport frames
at0→37.5%, samples the track inside each progress cell away from its label, and
separately verifies changing label pixels. Its strict verifier requires both
actual counts/endpoints. Deliberately omitting either origin correction or label
caused the actual Cocoa diagnostic to fail; both mutations were restored.
The original18measurement stages,90s cumulative budgets, worker/SQL/I/O and
selection/restart/collection gates are unchanged. Extra frame buffers mean this
fixture is not a paired retention comparison against older reports.

Local results: **948 Python passed in140.52s**, **29 Cocoa theme/paint/actual-
diagnostic tests passed in16.19s**, focused118passed9.13s, JavaScript10passed/
0skipped, protocol9/pipcheck/shell syntax passed. The same three test-only Qt
deprecations remain. Separate new45frame source captures preserve theme-only
evidence; inspected compact/standard/fullscreen and restored Light selected rows
show the correct progress column and visible percentages, with no title overpaint.
Synthetic fixture percentages reflect their stored fields, not live media tests.
Compact clipping, column allocation/details, dialogs and final hosted acceptance
remain unfinished; no release/install or Swift work was performed.

## Responsive presentation and discoverable actions

`queue_presentation.QueuePresentation` configures a bounded number of interactive
header sections on view, font and viewport changes, without job scans, SQL or
settings writes. Defaults show Title, Status, Progress, transfer speed, ETA and
Destination. Type, upload speed and other technical fields remain available under
Columns; explicit extra columns/custom widths may intentionally require scrolling.
Actual running-rate and long-ETA cell pixels are compared against wider cells:
dash-only idle fixtures had missed clipped units. Warning status width also has
a real native cell-image regression, not just a font-width assertion.

The queue uses smaller horizontal margins, useful remaining table height and a
collapsed-by-default Download details disclosure. Collection selectors stay next
to their labels. Sidebar collapse preserves accessible names and Meta1–5 routes.
Per-view visibility/widths and sidebar/details preferences are optional schema6
fields, sanitised without resetting authentication/runtime state. Ordinary Apply
merges only those four presentation fields from current UI state; Cancel and
explicit Reset retain their separate semantics. Preferences persist at existing
Apply/close boundaries, not on resize. Reset columns affects only the current view.

Destination shows the useful filename/folder, with the unchanged full path in
search, details and escaped tooltips. No filesystem lookup or domain path rewrite.
The Download connection result is a separate wrapped plain-text line, leaving
Test and Account controls accessible when a result is long.

Direct Clear Completed and its existing split-button menu remain. A named More
actions menu exposes failed retry, clear cancelled/failed/selected/current group,
cancel group and restart selected. Its collection actions capture scope when the
menu opens; a visible disabled heading is used because Cocoa omits menu sections.
Retry failed freezes UUIDs, confirms once, excludes live owners and rechecks
failure/membership per existing32-ID batch slice. Existing Resume authentication
policy alone refreshes account fields for recognized media auth failures; all
other captured options remain. Modal completion/moves are skipped, never broadened.

Local source full suite before the final scope-heading regression: **978 passed,
5 test-only Qt activation deprecations in145.56s**, zero skips; focused81passed
15.61s/native35passed8.71s. Additional all-view percentage characterization9passed
2.03s (no new paint fix). Companion10passed, protocol9/pipcheck/shell syntax pass.
Final task-boundary/full-checkpoint runs will supersede this intermediate count.
Final Task3 precommit suite: **988 passed,5 warnings in142.97s**, zero skips;
native layout/action/paint **45 passed,2 warnings in9.79s**. Scope heading was
observed RED at actual native0height and is now visibly present in a fresh popup.
Fresh source captures include nonzero transfers/long ETAs, all3queue views and
Light/Dark/System at requested sizes/fullscreen, with zero external I/O/final owners.
Reviewed compact Dark queue/Download and System menu; final all-page evidence and
same-fixture performance/hosted packaged qualification are still Task4 work.

## Counted dialogs and native disabled menus

Clear/restart/collection confirmations retain the existing result values, one
confirmation, Keep-files/Cancel defaults, scope/UUID rechecks and worker services.
Primary copy distinguishes clearing queue entries from deleting files, states
counts and warns that deletion may be permanent. Clear still tries Trash where
supported; restart replacement remains permanent. Recorded ownership, uncertain
preparation,32-ID slices, stop behavior and cleanup failures remain in expandable
Details, not lost or replaced by a claim of guaranteed Trash recovery.

The implementation uses the existing [Qt QMessageBox property API](https://doc.qt.io/qt-6/qmessagebox.html#the-property-based-api):
main/informative text is explicitly plain; detailed text is also plain. Tests open
real dialogs, expand Details and click actual Keep/destructive/Cancel/OK buttons,
checking the original results without executing file actions. Eight cases were
observed failing before the change;89 focused/native8 then passed. Source captures
cover collapsed/expanded dialogs in all3themes: clear691×161/283, restart689×177/299,
collection420×193/315 logical pixels, within the compact900×650 parent.

Actual System disabled menu text measured1.795:1 contrast. Explicit disabled-item
styling now uses the same adaptive opaque token as buttons. A follow-up pixel
test found that requiring ordinary4.5:1 contrast for disabled text selected black
on native#ececec because the dim candidate measured4.494:1. Disabled text now uses
the spec's3:1 minimum, remaining readable and visually distinct; normal semantic
text retains4.5:1. Both defects were independently observed RED before repair.
Native whole-checkpoint consumer command:74passed/5test-only warnings in26.88s.
Final local full suite:999passed/5test-only warnings in144.89s, zero skips.
Companion10passed/0skipped, protocol9fixtures match, pipcheck and shell syntax pass.
The same command is now required in hosted macOS CI, not substituted by Linux or
frozen progress-only checks. Hosted results remain pending at this writing.

Remaining visual limitation: the native decorative question-mark icon is faint
in Dark dialogs; primary text, counts and buttons remain readable. This is not
claimed as a completed professional icon/design-system pass. The audit's direct
theme changes leave the Settings form's pending Theme choice unchanged on purpose;
the actual Apply/Cancel behavior is independently tested.

## Same-fixture layout observation and remaining stalls

After all other owned tests/captures finished, the existing isolated offscreen
benchmark ran sequentially on `a5eb8ab` (theme/progress baseline) and current
layout/dialog source. Both use exactly the same diagnostic, one cycle, profiler
flag and synthetic1ms/job cleanup. These measure the layout increment, not all A
against the older broken-paint9ed build, and are single observations, not a
statistical performance or lifetime/leak qualification.

| Jobs | Original-stage max gap, before→after | Extra collection max gap | Peak RSS MiB |
| --- | --- | --- | --- |
| 800 | .119→.129s | .249→.250s | 180.59→181.84 |
| 5,000 | .739→.756s | 1.736→1.733s | 370.03→372.95 |

At5,000 original-stage wall14.488→14.597s, CPU7.984→8.080s and post-removal
RSS354.41→360.20MiB. SQL unchanged at26,279statements/633commits/25,004writes;
800 unchanged4,223/105/4,004. Both retain two maximum transfer owners, one cleanup
worker/32-job maximum slice, zero final owners and zero forbidden I/O. No
performance improvement or fixed retention is claimed from these values.

A separate whole-fixture profile attributes12.65s to12 diagnostic
`verified_reload` calls, including independent persistence checks/full dictionary
serialization, within47.74s profiled runtime. Collection assertions themselves
include repeated whole-queue comparisons, so their heartbeat gap cannot all be
attributed to application UI work. Application-side history refresh/search,
serialization/copies and structural queue refresh also remain substantial:
20 history refreshes4.43s cumulative,23 searches3.57s,22 queue syncs1.46s under
profiling. These overlapping cumulative values are not additive or unprofiled
latencies. The diagnostic/gates are unchanged; remaining stalls/long-running RSS
remain open, not erased because verification contributes cost.

## Final review and additional native appearance evidence

The single fresh reviewer read the complete `9ed1082..18e22bc` checkpoint and
integration paths. No Critical findings; one Important finding: the opaque
disabled token did not cover QToolButton. Native System Collection actions was
1.795:1 in the original full-window capture. New real-control tests reproduce
unreadable Collection/More actions after theme roundtrips, then verify both
readability and a distinct disabled state. The same token now covers QToolButton.
The minor retained Clear Completed scope heading also had native height zero:
it now uses a disabled ordinary action, matching More actions. Scope/UUID/action
execution is unchanged. Both defects were observed failing before correction.

The reviewer independently ran56 portable tests (two known test-only warnings).
Its native probe could not create a screen in its sandbox and is not counted as
a pass. Main-agent authorized own-window checks are separate evidence; no
Accessibility permission, live account access or local build was used.

A November7 native recapture produced72 frames with zero external I/O attempts,
zero final owners and empty stderr. This session uses System **dark**, unlike the
earlier System-light audit, and permits actual900×650/1180×820/1440×900 normal
windows and1920×1080 fullscreen. It exposed an additional native-palette issue:
AlternateBase#989898 behind white sidebar text gives2.885:1 contrast. The sidebar
now falls back to the native Window surface only when the alternate surface is
unreadable; it does not set or freeze the native palette. Visible/hidden late
dark-to-light regressions cover this, while preserving ordinary alternate surfaces
and unchanged-theme no-op behavior.

Final local verification after all corrections: **1,008 passed, 5 known test-only
Qt activation warnings in 197.65s**, no skips. Native Cocoa consumer suite:
**83 passed, 5 warnings in 39.05s**. JavaScript: 10 passed, zero skips; all nine
protocol fixtures match; pip check and `zsh -n build_macos.sh` pass (syntax only).
The preceding1,006-pass run predates the sidebar correction and is not the final
result. The new72-frame capture again records zero external I/O/final owners and
empty stderr. Inspected System-dark compact Queue/Settings/Download and fullscreen,
Light standard Queue, Dark compact Queue and the real scope popup confirm the
sidebar correction, readable disabled controls and visible heading. Native input
placeholder hints still look faint in System appearance; record for the broader
design-token pass, not a claim of complete accessibility qualification.

Exact-head hosted Linux/macOS/native/frozen/archive results are still pending.

### First hosted attempt: not qualified

Published source `136afd14eb7f38da48b11a4a887dc12c7ca61778`, run42376744385:
macOS backend60 passed and protocol9 matched. Cocoa UI returned81passed/2failed
in67.83s; both failures require400px queue height after requested1180×820 and
1440×900 window sizes, but observed286px. This is not labeled flaky and no
threshold is lowered. A diagnostic-only assertion update records actual window,
frame and screen geometry to distinguish platform clamping from a layout defect.
Swift build/tests and frozen packaging cannot be claimed on this failed run.

The diagnostic-only commit `3e13dba95a4db65a8a9ca96d6a2d5c7540d29090`, hosted
run42377309447, proved the native clamp: requested1180×820 and1440×900 both
became656px content height. Each684px frame exactly filled the screen's available
684px vertical space. Both native attempts returned81passes/2failures; this is
an invalid requested-height assumption, not evidence of an application shrink.
The test now retains250px at actual650px and400px at actual requested large sizes;
only verified Cocoa screen clamping can account for the missing height, never
below the compact250px minimum. Eight regressions retain the original thresholds
and reject offscreen/unexplained shrinkage or a window below650px. Large requested
sizes remain exercised exactly by Linux offscreen and the local native display;
hosted clamped cases are not advertised as actual820/900px native captures.

The first Linux attempt returned1,007passes/one failure in273.02s: real platform
font widths made ordinary All-view columns total702px in a696px viewport. The
second diagnostic attempt retained that failure (1,007passed/one failed in
225.44s). A regression reproduces those
measured widths before the fix. Automatic progress-track width now absorbs small
font-dependent differences while preserving the complete percentage, at least a
24px track,160px title and all status/rate/ETA text. It returns to100px when space
permits; explicit user widths are never overridden or saved as automatic choices.
The controller still touches only bounded header sections, not jobs/SQL/workers.
Focused portable28/native38passed; full native92passed34.19s with five known
test-only warnings. Final isolated full suite: **1,017 passed, five warnings in
164.28s**, no skips. New hosted/frozen qualification is still pending.

Still not qualified: existing History header/value clipping; native placeholder
hint contrast; faint native Dark
question icon; arbitrary enlarged fonts/localizations/displays; actual Qt6.7;
hardware-keyboard/OS focus/accessibility certification; live auth/media/Trash/
cross-volume behavior; long-lived retention and remaining stalls; B/C/D/E roadmap.
