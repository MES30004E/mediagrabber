# Durable development handover

Updated 2026-11-07. Active programme: Full Product Completion Mission; scope and
approval limits in PRODUCT_SPEC/FEATURE_BACKLOG/RELEASE_READINESS.

- Branch: `improvement/download-reliability`.
- Last qualified source: `b91faf2145b18d1c0995d369cc945d4b2c186c50`.
- Hosted run42383941374 attempt1: all jobs passed; strict actual frozen reports
  revalidated. QA_MATRIX lists counts/limits. No release/installation.
- Main remains6a024ec97d2521beed1c6cce2752aaa605425390; Swift bridge remains
  b603921f92dcf5238e6451ba46346ebe450bedfb; provider remains
  7608dd51ee813b48cf9a6d68c6e42cb197ce10e0. Do not reset/repin/merge them.
- At mission start: two owned uncommitted evidence updates in FEATURE_BACKLOG
  and UI_CORRECTNESS. Preserve unrelated untracked October4/18 analysis-preview
  drafts. New mission documentation and scheduler work may be newer than this
  checkpoint: inspect actual status/diff/HEAD before resuming, never assume clean.

## Exact next work

1. Old UI correctness evidence is closed with the verified final package result.
2. New P0 scheduler correction implemented and independently reviewed: capacity
   before snapshots, separate budgets/FIFO/captured inputs/activity preserved.
   RED12/1 → focused72/native13/full1,030pass169.54s, no skips. Paired idle5000
   median100.77→.279ms; no broad freeze claim. Published380e62b/run42382032289:
   Linux1,030/native92/backend60/Swift25/protocol9/JS10 and final package passed.
   380/e2f remain earlier qualified rollbacks; latest is b91 below.
3. Restart fix implemented: optional validated stable anchor and unique siblings.
   Keep old legacy nesting untouched; never derive ownership by stripping folder
   names. Cleanup still sees the current attempt before the new destination is
   assigned.23RED→56focused/39native/full1,055pass204.60s/no skips; independent
   review no blocker; committedbd17a36 after history/provider/index audit.
   Published with b91faf2; exact hosted packaging qualification passed.
   New RESTART_DESTINATIONS.md defines behavior and limits.
4. bd17a36 and hidden-History b91faf2 are published. Deferral is separately
   reviewed:6RED/2pass→48History
   tests/178expandednative/full1,063pass153.09s/no skips. Same-fixture5000×5queries5→0,
   cellwrites175000→0,median379.26→.0013ms. HISTORY_DEFERRAL.md records scope.
   Run42383941374: Linux1,063/JS10, macnative178/backend60/Swift25/protocol9 pass;
   packaged job128438124731 passed; strict actual four-size reports revalidated.
   Archive/replacement/signature/source-unchanged checks passed, no publication.
   Visible History/first stale-cell destruction and long-lived retention remain;
   distinguish diagnostic payload comparisons from actual app work.
5. B4 one-shot inspector/context-menu and failed-task-callback ownership fixes
   implemented/reviewed locally; EPHEMERAL_LIFECYCLE.md records RED proof/limits.
   Focused57/Cocoa23/expandednative201/full1,074passed150.24s, no skips; independent
   review11pass/no blocker; JS10/protocol9/pipcheck pass. Audit/commit after exact
   staged review; b91package has now passed and been inspected. These are
   narrow ownership fixes, not total RSS/leak or original freeze acceptance.
6. Continue mission milestones; real design research/proposals precede major UI,
   actual playback precedes Viewer acceptance, live private QA needs the user.

Use project Python, isolated test data and the standalone Git if Apple's Git is
licence-gated. No local build/sign/admin tools. Security gates before every push;
same exact-source hosted checks after a meaningful implementation checkpoint,
not repeated rebuilding of unchanged successful artefacts.
