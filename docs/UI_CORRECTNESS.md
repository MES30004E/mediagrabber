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
plus roundtrips, a details dialog and popup. The final audit records45 captures,
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
- Compact clipping, narrow titles, horizontal scrolling, oversized details,
  collection-row alignment and persisted responsive preferences.
- Discoverable remaining bulk actions and concise counted confirmation dialogs.
- Whole-checkpoint fresh review, full final tests/performance comparisons and
  exact-commit hosted packaged/macOS/Linux qualification.
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
