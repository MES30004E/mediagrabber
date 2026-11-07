# MediaGrabber UI design system

Status: **In Progress — professional redesign not yet researched or approved.**
This records established correctness constraints, not fabricated design approval.
FEATURE_BACKLOG U01 owns design research/proposals; UI_CORRECTNESS contains actual
native repair evidence. The original repository icon must be retained.

## Established interaction rules

- Simple paste/drop → analyse → preview/select → download → manage/play.
- Native PySide6; ordinary controls first, advanced options in named disclosures.
- Coherent Download/Queue/Library/History/Settings is the intended navigation;
  Library is not implemented yet. Console stays discoverable, not dominant.
- Light/Dark/System follow actual native palette updates, including hidden and
  dynamic controls. Current project contrast gates: ordinary text4.5:1 and
  disabled labels3:1; these are not full accessibility certification.
- Queue prioritises title, status, percentage, rate, ETA and useful destination.
  Optional technical columns and explicit widths remain user-controlled. Preserve
  stable UUID selection, readable defaults and persisted sidebar/details choices.
- Clear Completed remains direct; advanced/destructive controls have explicit
  labels and captured scopes. One counted confirmation, Keep/Cancel default;
  explain deletion versus entry removal. Technical detail is expandable.
- Known/unknown/estimated totals are distinct. No fake success, generic decorative
  dashboards, gradients or animation hiding backend work.
- Keyboard routes, focus, loading/error/disabled states and native resizing must
  survive visual changes. Never run expensive I/O from a paint/layout callback.

## Required design work before substantial redesign

Research current Apple HIG, official Qt/PySide6 and public Stacher/ClipGrab
interaction patterns with dated source links. Define typography, density/spacing,
palette/status tokens, reusable buttons/forms/tables/toolbars/menus/dialogs and
empty/loading/error/progress states. Do not copy proprietary artwork/code.

Produce coherent Download, Queue, Library, History and Settings proposals; compare
alternatives, record screen hierarchy and selected rationale, obtain approval
where required, then implement components incrementally. Screenshots of the real
app must be compared against proposals, not replaced by mock-up claims.

## Native visual QA

Actual900×650,1180×820,1440×900 plus fullscreen in all three appearances. Record
real OS-clamped dimensions instead of claiming requested dimensions were tested.
Inspect captions, input hints, selections, menus, disabled controls, dialogs,
long names, resizing, keyboard and error/recovery states. Include real playback
and file-missing states when Library exists. See QA_MATRIX for current evidence.

Remaining visible defects include History clipping, faint System placeholder
hints and the native Dark decorative question icon; broader typography/navigation
and personal branding are not solved by the completed correctness checkpoint.
