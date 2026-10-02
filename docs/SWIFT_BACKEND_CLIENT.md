# Swift backend client — Phase 2

`swift/` is a Foundation-only SwiftPM library, targeting macOS 12 with Swift tools
5.9. It implements the executable Phase 1 protocol, not the future durable
contract or an application UI. Qt continues its existing in-process path.

## Use and ownership

```swift
import MorganBackendClient

let client = BackendClient()
// Start consuming before operations; events has ONE consumer.
let consumer = Task {
    for try await message in client.events {
        // Reduce presentation state elsewhere; filter by message.requestID.
        // No raw command/event logging. message.operationError provides typed failures.
        _ = message
    }
}
let configuration = WorkerConfiguration(
    executable: pythonURL, workingDirectory: repositoryURL,
    environment: controlledEnvironment // includes PYTHONPATH=<repository>/src
)
let capabilities = try await client.start(configuration)
let response = try await client.send(.analyse(AnalysePayload(inputs: [":ytwatchlater"])))
// response is acceptance; completion/items arrive on events with its requestID.
_ = response
_ = capabilities
try await client.shutdown()
_ = try await consumer.value
```

Caller supplies an explicitly trusted Python executable and environment; the
library does not search PATH, install runtimes, construct shell strings, or put
credentials in arguments. One client owns one Process/session. Invoke shutdown
for a graceful drain; abort is the explicit fallback. A failed/stopped client is
not reusable: create a new client, reanalyse and reconcile manually. Never replay
mutations automatically. The worker state is ephemeral and has no Qt database.

Lifecycle is actor-isolated: idle → starting → ready → stopping → stopped, or
failed(BackendError). Start performs hello/version/capability negotiation before
allowing commands. Defaults: ten-second request/write and shutdown timeouts.
Caller can configure positive finite timeouts up to 300 seconds. This is not an
automatic heartbeat/reconnect service; send ping explicitly. No UI/state snapshot
or durable queue is implied by a successful handshake.

## Framing and concurrency

BackendCommand emits UTF-8 JSON followed by LF. JSON bytes are limited to 1048576,
excluding LF/CRLF. Incremental framing handles split UTF-8, CRLF and multiple
frames, retaining at most the maximum plus a possible framing CR. Oversize emits
one error and drains through LF; the standalone framer can recover. The live
client treats malformed/oversized output as session failure, discards untrusted
raw data and terminates its owned worker. Unknown event identifiers retain their
envelope but discard the unknown object payload. Known fields are typed; nullable
envelope keys must be present; additive unknown object fields are ignored.

One actor serializes session, sequence, request registry and continuations.
stdout and stderr use independent dedicated Dispatch queues; stderr bytes are
discarded without parsing or logging. stdout delivers bounded chunks through an
actor rendezvous, avoiding an unbounded task backlog. Writes use their own serial
queue and a nonblocking descriptor with bounded polling; no blocking pipe read or
write runs on the Swift cooperative executor. Darwin suppresses SIGPIPE only on
the owned write descriptor, not globally in the future host app.

The event stream buffers at most 512 events. A slow or cancelled consumer fails
the session rather than dropping terminal events silently. At most 128 requests
await replies; session request tombstones are bounded at 65536. Caller must drain
events continuously. This initial bridge prioritizes correct boundaries over
progress coalescing; no native download presentation is implemented.

## Correlation and cancellation

Each command gets a fresh UUID, a UTC timestamp and the negotiated session UUID.
Register it before queuing the write. Responses must match request/type/job ID;
events must reference known initiating requests, with analysis/download family
and source/job identities checked. The sequence must advance by one in the same
session. Unknown optional events remain available to the stream's consumer.
Uncorrelated error/diagnostic events may carry null request IDs.

Cancelling a Swift task cancels its local wait/write ticket; it does not assert
that accepted Python work stopped. Use analysis.cancel(target_request_id) or
jobs.cancel(job_id, expected_job_revision) for backend cooperative cancellation.
A partially sent frame makes the connection unusable. Matching late responses
after timeout/cancellation are discarded; nothing is replayed. Backend failure
and auth-required events expose operationError and remain correlated stream
messages rather than ending every unrelated operation's stream.

## Shutdown and failure

Shutdown first blocks new sends, then sends session.shutdown. The worker requests
cooperative cancellation and waits for existing operations; extraction and
processing can delay this. Swift continues draining both pipes until the final
response and stdout EOF/process exit. Termination callback ordering never
overrides final buffered stdout. Graceful completion requires acknowledged
shutdown plus exit zero; unsolicited exit zero is workerEOF, nonzero is
workerCrash(status). Remaining requests fail, including outstanding calls at graceful exit. EOF without
process exit gets a 250ms exit-notification grace period, then fails the session
and terminates ownership; acknowledged shutdown instead uses its bounded exit
timeout. Cancelling shutdown after acknowledgement releases its exit waiter and
aborts ownership promptly.

On timeout or protocol/transport failure, signal only the owned Process, close
stdin and escalate to SIGKILL after one second if it remains running. This may
interrupt an operation and does not prove engine descendants or output recovery
are qualified. No foreign/stale PID is read from storage. No destructive cleanup,
resume, restart or reconnect occurs. Explicit process abort is separate from
backend cooperative cancellation.

## Errors and privacy

BackendError distinguishes incompatible version, malformed/oversized frame,
EOF/crash, protocol rejection, operation failure, authentication, correlation,
timeout, cancellation, lifecycle, transport, capacity and slow-consumer failures.
Error descriptions are fixed text; they never include raw stderr/JSON, input URLs,
paths or exception dumps. Error code identifiers are grammar-checked. DTO values
are private local data: do not print or upload them. Unknown payloads and stderr
are discarded. No raw cookie, proxy password or Keychain-secret command exists.
The worker retains responsibility for its explicit redaction adapters.

## Tests and drift protection

Tests load the exact nine files under tests/protocol_fixtures/ using the source
checkout, without duplicating fixtures into Swift resources. Python's
scripts/check_backend_protocol.py compares version, frame limit, every canonical
command/event identifier and fixture capabilities with the Swift declarations.
Swift tests decode fixtures independently and check malformed/schema/version/
unknown/size/fragmented input plus lifecycle, correlation and cancellation.

Hosted macOS runs all Swift tests with MORGAN_TEST_PYTHON pointing to Python 3.12
installed by setup-python. Real worker integration requires that variable and
fails rather than skipping. Tests launch the actual module for hello/ping/shutdown
and the existing test-only external yt-dlp boundary for deterministic Watch Later
analysis. A separate synthetic transport peer floods stderr and simulates
crash/EOF/bad frames without network, cookies, Tor or accounts.

The Ubuntu job retains the full Python regression suite. macOS also runs Python
backend tests and drift protection. No owner's local Xcode, signing/notarisation,
packaging, UI launch or live accounts are involved. Source/test presence alone is
not a native success claim: hosted build/test results must be observed separately.
