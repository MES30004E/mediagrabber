# Bounded Queue Actions Implementation Plan

**Goal:** Connect atomic persistence to responsive large pause/resume/cancel actions, without creating per-job threads or pretending that removal/restart/model-view work is complete.

**Execution:** Inline existing checkout, Superpowers TDD/verification/review. User authorized autonomous incremental work. Preserve unrelated drafts, main/Swift/provider and current hosted run40993057336; no local Apple tools, personal media/auth, installation or release.

1. Implement GUI-owned `QueueBatch`: one operation admitted, one timer,32IDs per queued slice, cancellation, bounded redacted error and completed/failed/unchanged/pending counts. Tests:yieldbeforework/interleaving,800IDs bounded/order,second admissionrefusal,mid-slice cancellation,continuedworkafteratomicfailure. InitialmissingmoduleREDthenGREEN.
2. Connect large>32 pause/resume/cancel using captured applied settings and copied current jobs; one atomic slice writes before live publication/worker cancellation. Dispatch waits, Stopbatch cancelsremaining, close stopsfuture slices. Small existingactions remain immediate. UItests:large800cancelinitialREDsync→GREEN25commits,stopbeforeworkleavesstate/workersunchanged,failedsliceleavesstate/DB/workersconsistent. Update benchmark to await asynccompletion while sampling heartbeat.
3. Full suite/JS/drift, measured800/5000 probes, one read-only checkpoint review and regressionfixpass. Update backlog/evidence with actual limitations. Commit locally, audit before a later push only after live hostedrun isterminal.

## Acceptance and retained scope

Each slice completes/rollsback before the next event turn. No worker mutates Qt. Pending work is not dispatchable midbatch; stopping leaves unprocessed IDs unchanged and reports them. Atomic failures don't cancel owned workers or publish failed copies. No unbounded error-list retention. Real network cancellation races, source-native crash, memory/model-view,asyncremoval/owned-fileIO/restart/collectioncontrols and GUI rendering costs remain separate acceptance gates. Total action time is not promised faster; responsive yielding is the goal.
