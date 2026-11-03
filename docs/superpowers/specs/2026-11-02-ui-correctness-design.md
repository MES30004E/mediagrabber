# Checkpoint A — native UI correctness and usability

## Intent and baseline

Implement the2November Product Quality steering directive's Checkpoint A, not
the subsequent substantial redesign/rebrand/viewer work. Simple by default,
advanced behavior discoverable; no correctness, data-safety or performance loss.
Rollback source9ed1082fbdace1bc5fea7a6943666c759881a80d/run41385802502 passed
Linux913,macOSbackend60/Swift25/drift9 and full native/strict-archive gates.
Three current qualification-doc edits are owned work; preserve them and October
4/18 migration drafts. Use current checkout/improvement/download-reliability.

## Evidence, not a new visual product architecture

Read-only39-frame real Cocoa audit of Download/Queue/History/Settings and native
fullscreen with synthetic800jobs reproduced unreadable Dark labels and light
sidebar/table. Same-stylesheet reapplication inside a temporary process fixes
most child colors but leaves a black navigation arrow, layout and possible
mispositioned native progress painting. The latter needs classification before
fixing; do not assume snapshot artifacts are user-visible failures. The audit's
requested1440x900 normal windows were OS-clamped around814high; native fullscreen
was1470x923. Offscreen logical-size checks cannot substitute for those records.
Baseline evidence remains read-only in the ignored collection-plan workspace.

## Approach and boundary

Repair the existing Qt shell, models, cached roles, bounded services and settings.
No framework/navigation rewrite. A fresh tree/web layout would replace qualified
behavior; a root-palette-only patch already demonstrably fails. Theme work keeps
the apply_theme(application,mode)->None interface, fixes actual existing/dynamic
widgets and respects Light/Dark/System. Research supported Qt APIs before using
native color-scheme requests; retain declared PySide6 compatibility. Recompute
QSS only when necessary, not on every unchanged apply/progress event. Semantic
text/focus/selection/disabled/menu colors must remain readable. Preserve the
normal body/navigation contrast target4.5:1 and disabled-label target3:1 against
their actual backgrounds; this is a project readability gate, not a blanket
accessibility-certification claim. Preserve the
original application icon; fix unreadable navigation glyphs without inventing
a replacement product icon or changing public branding in this checkpoint.

## Conservative queue layout

Keep the present information order, improve allocation rather than create cards:

```text
Collection selector · actual status/progress · collection actions
Search · status/view filters · optional columns
Selection/counts · frequent actions · Clear Completed · More actions
Queue table uses remaining area; meaningful title/status/progress/speed/ETA/folder
Details disclosure (collapsed by default, user preference retained)
```

Keep labels/controls left-aligned; wrap compact toolbar groups instead of clipping.
Default ordinary columns fit900x650,1180x820,1440x900; technical columns remain
available in a named Columns menu and full details. Retain all data/roles/search
and UUID selection; explicit user column choices may intentionally require scroll.
Remember per-view column/detail/sidebar preferences with backward-compatible
defaults; only persist at normal settings/close boundaries, not every progress or
resize. A reasonable collapsible sidebar retains Meta1–5 and accessible labels.
Do not erase an existing preference during unrelated Settings Apply/Cancel.

## Actions and language

Clear Completed stays direct. Pause/resume selected and retry failed are easy to
find; clear selected/cancelled/failed/current collection, cancel collection and
restart selected remain discoverable without duplicating toolbars per job.
One actual named scope/count confirmation at most, files kept by default. Reuse
QueueBatch/FileRemoval/QueueRestart and their immutable-ID/eligibility/owner-drain
rules. Retry failed uses current auth settings only through existing retry policy.
Completed work never becomes runnable through pause/cancel/resume races.

Concise primary dialogs say queue removal versus deleting files created by this
app. Explicit destructive choice; accurately explain Trash/permanent limits.
Technical inventory,32-ID/worker/persistence wording moves into expandable detail,
not lost diagnostics. Unknown progress shows known/unknown/completed counts, not
an unjustified full bar; no title-based grouping or data/schema/wire redesign.

## Acceptance and unfinished scope

TDD theme roundtrips/no-op/dynamic dialogs/menu/focus/disabled/icon contrast;
classify and regress native progress coordinates before changing its renderer.
Real900x650/1180x820/1440x900 logical-size plus actual Cocoa/fullscreen renders,
keyboard/filters/selection/menus and saved preference roundtrips. Synthetic800/
5000 actions/SQL/workers/latency/RSS measurements and exact frozen qualification
must not silently disappear or weaken. Baseline5000extra gap4.817s/retention is
still a release blocker, not the responsiveness target. Profile measured remaining
work rather than claiming theme/layout solves it.

No local Apple build/signing/admin/Homebrew tools. No personal auth/media use,
release/upload/install/launcher or protected-branch/Swift work. Before every push,
scan allrefs/reflogs/history, provider and exact index, triage known public
constants, verify Public. One final fresh read-only review/one blocking TDD fix
pass; no implementer agents. Major B redesign needs researched visual proposals/
approval; C rebrand preserves data/Keychain/extension identities; D real Viewer
and all FEATURE_BACKLOG commitments remain unfinished until actually verified.
