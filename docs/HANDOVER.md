# Durable development handover

Updated 2026-11-07. Active programme: Full Product Completion Mission; scope and
approval limits in PRODUCT_SPEC/FEATURE_BACKLOG/RELEASE_READINESS.

- Branch: `improvement/download-reliability`.
- Last qualified source/local checkpoint: `e2f3ea33009610ae6bcf26dd06686ed33a539f33`.
- Hosted run42378146636 attempt2: all jobs passed; strict actual frozen reports
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
   Linux1,030/native92/backend60/Swift25/protocol9/JS10 passed, final package pending.
   Until all gates are inspected, e2f remains the qualified rollback.
3. Restart fix implemented: optional validated stable anchor and unique siblings.
   Keep old legacy nesting untouched; never derive ownership by stripping folder
   names. Cleanup still sees the current attempt before the new destination is
   assigned.23RED→56focused/39native/full1,055pass204.60s/no skips; independent
   review no blocker. Exact staged security review, commit/push/hosted qualification next.
   New RESTART_DESTINATIONS.md defines behavior and limits.
4. Profile actual History rebuilds and long-lived retention separately from
   expensive diagnostic reload/payload comparisons. Do not label all observed
   synthetic gap time as the user's real freeze.
5. Continue mission milestones; real design research/proposals precede major UI,
   actual playback precedes Viewer acceptance, live private QA needs the user.

Use project Python, isolated test data and the standalone Git if Apple's Git is
licence-gated. No local build/sign/admin tools. Security gates before every push;
same exact-source hosted checks after a meaningful implementation checkpoint,
not repeated rebuilding of unchanged successful artefacts.
