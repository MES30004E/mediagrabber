# P0 scheduler capacity-before-snapshot correction

Status: locally verified; hosted qualification pending. Source rollback:
e2f3ea33009610ae6bcf26dd06686ed33a539f33. Feature ledger Q01/Q11/A01 remains
In Progress because other stalls and retention have not been resolved.

## Cause and change

`MainWindow._dispatch` runs every500ms and copied all AppSettings for every
Waiting job before checking its type's free slots. With two media owners and an
unused torrent budget, an all-media5000job queue made24,990 unnecessary copies
across five no-op ticks. Existing synthetic queue fixtures stop the repeating
timer and therefore do not measure this ongoing production scheduling cost.

Check the appropriate capacity first; for media validate its route before copying.
Retain one independent job/settings/runtime/route capture per admitted task,
per-kind FIFO and budgets, busy-batch exclusion and the final activity update.
Stop the loop when both budgets are exhausted. Waiting-list construction remains
O(N). No new I/O, threads, persistence semantics or route/auth fallback.

## Regressions and review

`tests/test_dispatch_capacity.py`: exhausted media/torrent/both budgets at800 and
5000, mixed ordering, exact copies/starts/writes, independent worker captures,
rejected media routes without torrent starvation, and busy-batch gating.
Observed12 failures/one pass before the implementation. All13 pass afterward;
focused scheduler/lifecycle/bulk/history72pass14.42s; native Cocoa13pass3.03s.
Independent read-only review found no blocking production issue.

First full-suite attempt in the restricted execution sandbox:1009passed/21failed
117.99s. Failures were blocked own-process `/bin/ps` memory measurements and the
unique synthetic Keychain write. The unchanged suite with normal test permission
passed **1,030 tests, five existing test-only warnings in169.54s**, no skips.
The restricted failure is retained, not relabeled as success. JavaScript10pass,
protocol9match and pip check pass. Exact new hosted qualification remains pending.

A new test initially left a fake queue service installed into real window teardown,
causing a reproducible native fault in the following lifecycle test. Excluding
that case isolated it; scoping the fake restores the real service before close.
All14 scheduler-plus-lifecycle cases then passed3.33s, with no assertion removed.
This fixture defect is not evidence of the user's reported production freeze.

## Same-fixture idle dispatch observations

Ten calls per size, fresh process before/after, actual Qt MainWindow with temporary
settings, synthetic jobs, two synthetic active owners and blocked external I/O.
No concurrent benchmark, actual transfer or private account. Medians in ms:

| Jobs | Wall before → after | CPU before → after |
| ---: | ---: | ---: |
|100|1.877 →0.010|1.877 →0.011|
|800|15.587 →0.053|15.587 →0.052|
|1000|19.392 →0.061|19.377 →0.061|
|5000|100.768 →0.279|100.339 →0.279|

5000max observed call102.767→0.507ms. Deterministic copy-count assertions, not
these timings, are regression gates. Zero external attempts/final owners.
Ignored probe/evidence lives in `.superpowers/sdd/2026-11-02-ui-correctness/`
(`dispatch_probe.py`, `dispatch-before.json`, `dispatch-after.json`).

Next: stable restart attempt anchor, actual History reconstruction costs,
long-lived memory and production-timer profiling. Diagnostic `verified_reload`
serialization also contributes to measured large-fixture gaps; distinguish it
from real application work. Preserve all frozen/persistence/ownership gates.
