# Isolated packaged queue-scale diagnostic

## Why and scope

Source/model tests and an empty frozen Cocoa window cannot establish large-queue
behavior in the actual bundle. Extend the opt-in startup diagnostic to exercise
real analysis presentation, enqueue, two owned synthetic workers, pause/resume,
cancel, persisted reload and keep-files removal at100/800/1,000/5,000 items.
Run two cycles per packaged case and report actual timing/heartbeat/memory/thread/
transaction evidence. This is not real transfer/account/Trash or leak qualification.

## Approach and ownership

Chosen engineering approach under the user's autonomous P0 instructions: extract
the existing benchmark's exercise into `queue_check.py` and consume it from both
the source benchmark and the packaged startup checker. Keep GUI construction,
isolation and QApplication ownership in their existing callers. Do not import
developer scripts/tests into the bundle or add testing methods to MainWindow.
An independent fake-native harness would duplicate behavior; running the source
benchmark alone would not test frozen Cocoa/ownership. Normal startup is unchanged.

`--startup-check REPORT --queue-items COUNT` explicitly requests the new mode.
COUNT must be100/800/1000/5000. Existing startup check remains without queue data.
Each packaged subprocess is fresh, frozen/Cocoa verified, report is non-overwriting
and bounded, bundled dependencies remain contained, shutdown must actually drain.
Two cycles retain no queue entries/tasks and use one removal confirmation request
each. Native crash/launch failure records exit status and only bounded/redacted
faulthandler stack lines; no arbitrary child stdout/stderr dumping.

## Safety and truthful evidence

Refuse nonempty queue/history/task state and paths outside the caller's disposable
root. Anonymous settings only; no cookies/browser profiles/proxy credentials.
Disable startup timers, clipboard/provider/network/update work. Guard socket
connections, Keychain operations and deletion helpers; replace only media transfer
with cancellation-driven synthetic workers, preserving TaskManager/GUI/DB/actions.
Only synthetic metadata/example.test URLs and empty owned-file inventories.
No real media, downloads or personal files are deleted or contacted. Unknown or
partial results, wrong counts/platform/source mode and remaining owners fail.

Metrics are observations, not fabricated hard real-time or leak guarantees.
Record peak and current RSS where available, sampled native thread counts versus
exact owned-worker high-water, heartbeat gaps, SQL writes/commits and cycle state.
No latency budgets are inferred from one CI sample; native crashes remain
unreproduced unless a trace actually establishes one. Never replace strict archive
verification or existing tests. No tests skipped for green CI.

## Boundaries and acceptance

Stay existing checkout; protect drafts/main/Swift/provider. No local Apple tools,
admin, personal accounts, release/upload/install, or destination decision.
Hosted macOS performs actual frozen native qualification after audited push.
Current59a757c run41169869112 must not be cancelled/superseded by a new push.

TDD: source isolated CLI cases and two real worker cycles, no network/Keychain/
deletion, nonempty-state refusal, old CLI/report behavior, malformed/partial/native
report rejection and crash-trace redaction. Keep the original benchmark's stage
contracts and all existing application tests. One final read-only review/fix pass.
Publish only audited development source, inspect exact hosted outcomes, retain
full FEATURE_BACKLOG and remaining native/user QA requirements.
