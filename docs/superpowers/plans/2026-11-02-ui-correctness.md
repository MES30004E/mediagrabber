# Native UI Correctness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans inline with TDD and one fresh final review. No implementer agents.

**Goal:** Complete Checkpoint A theme, progress, responsive queue and action clarity.
**Architecture:** existing Qt shell/models/services; focused presentation helpers;
no backend/data/identity rewrite or substantial B design implementation.
**Tech Stack:** current Python3.12/PySide6, SQLite JSON/settings, existing CI.
**Spec:** docs/superpowers/specs/2026-11-02-ui-correctness-design.md.

## Global Constraints

Same checkout/branch; source rollback9ed1082/run41385802502. Preserve owned3doc
edits and2unrelatedOctdrafts. No local Apple/admin/build tools, personal accounts/
media, release/upload/install, protected merges or Swift work. Existing icon/IDs
stay. Full913/JS10/drift9/native4sizes2cycles/strict-archive gates retained.
Every push: allrefs/reflogs/history/provider/exact-index scans/Public verification.

## Review Focus

- Theme switches while menus/dialogs or hidden pages exist must not leave stale
  child colors, lose selected/focus states or repeatedly repolish unchanged UI.
- Compact/custom columns and saved settings must not hide actions, change UUID
  targets or overwrite unrelated preferences through Apply/Cancel.
- Native progress clipping/RTL/selection/unknown values must paint only inside
  the intended cell without per-row widgets or native resource growth.
- Modal updates and deferred owners must not broaden retries/deletion or make
  completed work runnable; retain actual outcomes after partial failures.
- Normal/fullscreen geometry, System appearance changes and untrusted long labels
  must remain readable/accessibly navigable without disk writes per UI event.

### Task 1: Actual theme propagation and semantic readability

Files: theme.py/ui_components.py; ui.py presentation-only status-label wiring;
new tests/test_theme_ui.py (actual consumer widgets), corrected Qt timing contract
in test_ui_refresh.py and test-only accepted/drained/deferred window teardown.
Interface: apply_theme(application,mode)->None unchanged; theme-owned helpers
may be private; any navigation icon refresh is bounded to the shell, not jobs.
- [x] RED existing sidebar/table/text Light→Dark→Light/System pixels/roles,
  existing/new menu/dialog/scroll/splitter controls, selected/disabled/focus colors
  and unreadable arrow; test unchanged apply does no repeated style event work.
- [x] Research actual Qt6.11/6.12/native scheme API compatibility; implement only
  proven propagation/semantic/glyph corrections in theme/shell, not new layout.
- [x] GREEN focused theme/settings/UI tests; full suite; actual source Cocoa
  before/after/roundtrip captures inspected. Commit coherent theme component.

### Task 2: Native progress correctness

Files: queue_model.py; queue model/paint tests; queue_check.py/check_packaged_app.py
only if new honest native evidence is needed.
Consumes current PROGRESS_ROLE/DisplayRole, exposes same delegate interface.
- [x] Reproduce suspected Cocoa coordinate issue with independent expected cell
  bounds/pixel evidence and zero→25→100/unknown/RTL/selected/disabled states;
  distinguish QWidget capture behavior from onscreen/native renderer limitations.
- [x] RED proven defect; smallest paint correction, painter state restored/no
  per-row QWidget/QObject. GREEN old paint/model tests and Cocoa real captures.

### Task 3: Responsive presentation and discoverable actions

Files: ui.py/ui_components.py/collection_controls.py/settings.py/settings_window.py;
focused queue presentation helper and conservative native reflow; queue_model.py cached
destination/status presentation; queue/selection/settings/layout tests.
Consumes stable UUID proxy, QueueBatch and captured scope APIs unchanged.
Interface: controller reflows on viewport/view/user preference, not progress;
defaults/backward-compatible saved detail/sidebar/column preferences.
- [x] RED900/1180/1440 bounds, useful table space, left-aligned collection
  controls, title priority, optional technical columns, collapsed details,
  sidebar/Meta1–5 and state roundtrip/ApplyCancel tests.
- [x] Implement conservative native reflow/details/column/sidebar helpers;
  preserve all data/actions and no model rescan/SQL/settings write on resize.
- [x] RED direct/common versus More actions, retry-failed scope/one confirmation/
  auth policy, moved/completed targets and hidden selection. Reuse services;
  GREEN800/5000/existing selection/restart/clear tests.

### Task 4: Human dialogs, complete evidence and qualification

Files: ui.py or small dialog module; dialog/collection tests; diagnostic gates;
FEATURE_BACKLOG/CURRENT_ARCHITECTURE and new UI correctness evidence document.
- [x] RED concise counted plaintext default-Keep/Cancel dialogs at compact parent;
  expand full diagnostics; preserve deletion/restart/stop semantics and errors.
- [x] Actual before/after Light/Dark/System pages/native fullscreen and keyboard/
  menu/error/disabled/loading states inspected; record actual OS-clamped geometry.
- [ ] Same-fixture performance/SQL/workers/RSS before/after, profile remaining
  stalls honestly; full Python/JS/drift/pipcheck and native qualification gates.
- [ ] One fresh final read-only review, one blocking-finding RED→GREEN fix pass/
  full suite; minors/exclusions explicit. Audited commit/nonforce push/exact CI
  logs+JSON/archive, no release/install; retain entire B/C/D/E and P0 backlog.

November7 local evidence: single review complete; Important toolbar/Minor heading
fixed RED→GREEN, additional actual System-dark sidebar correction verified.
Full1,008passed197.65s/native83passed39.05s/JS10/protocol9/pipcheck/syntax pass,
zero skips; actual72-frame final native capture. Hosted/frozen publication gate
remains outstanding, so Task4 is not complete. Hosted runs42376744385/42377309447
exposed platform-font compact overflow and proved native screen height clamping.
Focused source/test fixes retain readable width and original unclamped minima;
final local1,017passed164.28s/native92passed34.19s. New hosted/frozen run required.

Self-review: Task1 preserves API used by all pages/Task3; Task2 keeps roles used
by selection/diagnostics. Task3 uses current scope/service interfaces, not duplicate
execution paths; Task4 tests those actual controls and documents unchanged limits.
