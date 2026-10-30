# Bounded Keep-Files Removal Plan

**Goal:** Make the safe-default bulk removal path yield and count owned-worker completion truthfully, retaining the full P0 backlog.

**Execution:** Existing development checkout, inline Superpowers TDD and one independent review/fix pass. Preserve main/Swift/provider and unrelated drafts. No personal accounts, actual media deletion, Apple tools, installation or release publication. Don't push over a live CI run.

1. Extend QueueBatch with immutable BatchOutcome and correlated waiting-ID settlement. Validate counts; don't call worker-stop requests completed until settlement. Cancellation stops future slices but retains admitted in-flight work; close abandons pending callback accounting without touching files. Unit pending/stop/error tests RED→GREEN.
2. Connect large keep-files removal to32-ID atomic database deletes. Remove from live dict only after persistence; retain pending active entries until owned task callback. Explicit delete-files choice retains original behavior and is NOT claimed asynchronous. Tests800yield/oneconfirm/25commits, real2ownedthreads, faileddeferredDBentry retained/stoppedstateInterrupted.
3. Independent review/fixpass: remove supersedes older pendingrestart so keep-files never invokes restart-deletion helper; blank-error fallback must count failed removal. Both findings reproduced RED then GREEN. Full suite/JS/drift and measured800/5000 default removal. Audit all refs/provider/exact index/Public state before any development push. No broad native-crash/memory/release claim.

Remaining gates: asynchronous optional file deletion, bulk restart, collection controls, model/view memory and native/real-media QA. Stop notification while waiting on admitted workers is a deferred UI coverage/polish item, not permission to report those entries completed.
