# Backend protocol v1 — design for review

This specifies future Swift ↔ Python communication. Nothing here is implemented.
The Python API worker is authoritative for jobs, retries, inventories and storage.

## Transport and envelope

Swift owns one local worker Process, stdin for commands, stdout exclusively for
UTF-8 JSON objects separated by LF, stderr for redacted diagnostic output. No
shell interpolation, listening network port, or human-readable progress parsing.
Concurrent worker tasks serialize writes through one writer. Reader buffers may
split/multiply frames; a newline completes one frame. Maximum frame 1 MiB;
maximum queued commands 128; oversized analysis/snapshots use pages of at most
100 items and must also satisfy the byte limit. Limits are advertised at hello.

All messages have `protocol_version` (major.minor string), `kind`
(command/response/event), `type`, `request_id` (UUID or null), `session_id`
(worker-assigned UUID, null only in client hello), `job_id` and `source_id`
(nullable opaque IDs), `timestamp` (UTC RFC3339), and object `payload`.
Worker messages also include monotonically increasing `sequence` per session.
Job mutations/events include `job_revision` and `attempt_id` (nullable until
dispatch). UUIDs must not contain media URLs or filesystem paths.

```json
{"protocol_version":"1.0","kind":"command","type":"analysis.start","request_id":"15135388-265e-48b7-a98c-60c6213230ab","session_id":"129e6c83-e4d9-4e50-bcac-a134e7ed917e","job_id":null,"source_id":null,"timestamp":"2026-10-01T12:00:00Z","payload":{"inputs":["https://www.youtube.com/watch?v=fixture"],"purpose":"preview","settings_revision":7}}
```

Input URLs and user-local paths may exist in private command fields because the
worker needs them. They must not be echoed wholesale in errors or telemetry.
`source_id` identifies an analysis result within its session; enqueue uses a
worker-held item reference and selected IDs, not an unvalidated extractor dump.
Persist source IDs with queued jobs so later snapshots preserve identity; a
lost transient analysis session requires new analysis before enqueue.

## Handshake and compatibility

Client sends `session.hello` with supported major/minor versions and capability
requests; worker replies with selected version, session_id, backend/build/runtime
versions, capabilities and frame limits. No mutation before success. Major
mismatch fails with `protocol.unsupported_version`; minor selects the highest
common supported version. Additive optional fields may be ignored. Unknown
commands receive `protocol.unknown_command`; unknown optional events may be
ignored, while a missing mandatory capability blocks the relevant operation.
Adding/removing required fields or changing state semantics needs a major version.

Client then requests `state.snapshot` and `settings.get`. Snapshot is a consistent
revision at `snapshot_sequence`; page events carry snapshot_id/page_index/final.
Worker buffers events produced after that revision until final page delivery.
Client replaces state atomically then applies buffered events in sequence.
New clients must not replay events from an older session. Unknown job status maps
to an explicit unavailable state and triggers resync, never Completed.

## Commands and outcomes

| Commands | Required payload and behavior |
| --- | --- |
| analysis.start / analysis.cancel | Inputs, purpose preview/direct, settings_revision; cancellation targets the original analysis request_id |
| jobs.enqueue | Analysis request_id, source IDs, selected torrent indices if applicable, validated options and routing/settings revision |
| jobs.pause / jobs.cancel / jobs.resume / jobs.retry | Job ID and expected_job_revision; distinct intent, partial data retained |
| jobs.restart | Expected revision and final_file_policy keep/replace; explicit user confirmation for replacement; wait for old task exit |
| jobs.remove | Expected revision and disposition list_only/delete_owned; no arbitrary deletion paths |
| jobs.list / history.search / state.snapshot | Cursor and limit ≤100; history query/status filters; snapshot consistency as above |
| files.prepare_action / files.complete_action | Job ID, expected revision, inventory ID, action open/reveal/trash; worker grants validated path and short-lived token; result reports native action outcome |
| settings.get / settings.apply | Typed settings, expected_settings_revision; credentials excluded; apply validates and writes atomically |
| auth.test / network.test / provider.check | Settings revision and purpose; report auth and routing scope honestly |
| secrets.bind | Keychain-derived ephemeral credential, routing reference; memory-only, redacted, session-scoped, never an event field |
| tor.start / tor.stop / tor.new_circuit | Only owned Managed Tor; cooldown/ownership enforced; external endpoint has no stop command |
| conversion.analyse / conversion.start / conversion.cancel | Source/output grants, typed ConversionOptions, overwrite confirmation, operation ID; cancel requires qualified engine capability |
| runtime.check / runtime.install / runtime.rollback / runtime.use_bundled | Official release selector; no arbitrary executable URL; affect future attempts |
| session.ping / session.shutdown | Liveness and graceful cancellation/drain; shutdown response only after ownership released |

Every validated command gets one response with the same request_id and type,
payload `status: accepted|completed|rejected` and either result or safe error.
Accepted is not a successful completed download. Async operations have exactly
one terminal outcome per operation or attempt: completed, failed, cancelled,
paused, or interrupted where that operation supports the state. For downloads,
job.paused/job.cancelled/job.interrupted terminate the attempt without implying
download.completed; a later Resume creates a new attempt_id.
Events retain the initiating request_id; runtime background events may use null.
Pause changes job status to Paused once worker exit is confirmed and emits
`job.paused`; Cancel confirms quiescence with `job.cancelled`. Analysis cancel
uses `analysis.cancelled`; conversion cancel uses `conversion.cancelled`.

Response example: same envelope fields as command, `kind: response`, `sequence`,
payload `{"status":"accepted","operation_id":"opaque UUID"}`. Validation
errors return rejected without changing persistent state. A revision conflict
returns `state.conflict`; client refreshes and obtains any needed confirmation
again rather than silently mutating newer state.

## Events and payloads

| Event types | Payload contract |
| --- | --- |
| analysis.started / item / completed / failed / cancelled | Operation ID; item events include source_id, safe MediaItem fields, collection/index, confidence; completion includes count and effective auth; failure uses Error |
| download.started | Attempt ID, captured runtime/options/settings revisions, resolved playable-format summary; starts after format resolution |
| download.progress | Stage, downloaded_bytes, total_bytes nullable, total_is_estimate, percent nullable (0–100), speed_bytes_per_second, eta_seconds nullable, fragment_index/count nullable |
| download.processing | Stage merge/conversion/subtitles/metadata/artwork/verification; stage percent nullable, never implied overall completion |
| download.completed / failed | Completed includes verified output inventory, warnings and verification; failed includes Error and retry options |
| job.changed / paused / cancelled / interrupted / removed | Authoritative sanitized job snapshot or removed ID; new job_revision; intent and retained-file disposition |
| auth.required / auth.failed | Mode, browser/profile selection status, safe reason, available user actions; never credentials |
| runtime.updated / runtime.failed | Previous/current version and source, verification/compatibility outcome; no artifact contents |
| torrent.progress | Download/upload bytes per second, bytes/total, peers CN, seeds SD, metadata/seeding stage; no fabricated swarm estimate |
| conversion.started / progress / completed / failed / cancelled | Operation ID, validated plan, stage progress; completed requires atomic publish and verification |
| tor.state / provider.state / network.state | Independent process/bootstrap/endpoint/Internet/target/provider observations; timestamps and tested scope |
| console.entry | Source, level, job ID, diagnostic category, redacted bounded message |

MediaItem allows title/uploader/duration, sanitized original/webpage URL, collection
metadata, subtitle languages and candidate confidence. Thumbnail preview uses an
opaque backend cache reference; request headers and signed thumbnail URLs remain
worker-private. Job snapshots expose durable fields described in SWIFT_ARCHITECTURE,
but exclude credential values, internal task pointers and request headers.
Verified file paths are private local DTO fields, never Console diagnostics.
Unknown byte totals stay null, not 0% masquerading as known progress.

Error object: `code`, `category` (input/auth/extraction/format/transfer/processing/
verification/network/provider/runtime/storage/protocol), `stage`, `safe_message`,
`retryable`, `retry_options`, `diagnostic_id`; optional safe bounded details.
Use stable codes such as auth.required, formats.none_playable, transfer.http_403,
media.verification_failed, worker.interrupted. No raw exception/traceback strings.
One 403 metadata refresh remains a bounded backend policy, not a frontend retry
loop. Completed-with-warnings remains distinguishable from Failed.

## Ordering, idempotency, and backpressure

Mutations are serialized through the state owner. Persist transition before
emitting the corresponding durable event. Increment job_revision on accepted
state changes; an attempt_id identifies one engine execution. Per-session
sequence detects missing events; on gaps resync, not guessed progress. Repeated
request IDs in the same session return the recorded response and do not repeat
side effects; retain the most recent 4096 responses and compact seen-ID tombstones
for all earlier requests. An expired duplicate returns `request.expired` and
requires snapshot lookup, not automatic re-execution. Limit a session to 65536
commands; after that drain operations and require a fresh session, bounding the
tombstone storage without confusing an old request with a new one.
Across worker restarts there is no guaranteed exactly-once execution: reconcile
job IDs/snapshots before retrying any mutation.

Progress is coalesced to ≤10 events/second/job. Terminal events, errors and command
responses cannot be dropped. Bound output buffering to 8 MiB; when pipe delivery
stalls, stop accepting commands and pause new dispatch. If blocked for 10 seconds,
request cooperative cancellation and shut down safely. Preserve inventories and
mark unresolved active work Interrupted at next startup. Swift reads stdout and
stderr independently so diagnostic output cannot deadlock framed IPC.

## Failure and security handling

Invalid JSON/schema/oversized messages yield a bounded protocol error without
echoing the raw line. Three consecutive malformed frames close the session.
An oversized line is discarded up to LF with bounded storage. Request validation
precedes engine work and forbids arbitrary executable paths/update origins.
Client handshake timeout 10 seconds; ping every 5 seconds, no reply for 15 seconds
marks connection unavailable. This does not mean a download has stopped: terminate
only owned worker resources after graceful shutdown attempts, then resynchronize.

On EOF/process crash, native UI freezes mutations and marks displayed active work
as connection-lost pending authoritative recovery. Restart yields a fresh session,
Database converts active states to Interrupted, no automatic resume/restart.
Owned child processes need startup PID/command validation and orphan recovery;
never kill a foreign process by a stale numeric PID alone. Runtime updates and
destructive file actions are not replayed on reconnect.

Private local pipes carry minimum necessary input/credentials. Launch with
controlled environment, do not place credentials in argv or process logs, and
never upload these streams. Worker DTO construction uses field allowlists plus
existing redaction; Swift applies defense-in-depth redaction. Local diagnostic
exports omit query strings, cookie/profile paths and secret-bearing values.

Native file-action grants are limited to one quiescent job, action and inventory
revision and expire after 30 seconds. Persist an action intent before issuing a
Trash grant and hold that job out of dispatch until the result is reconciled.
If the client crashes after moving a file but before confirming, inspect exact
recorded paths on reconnect and report an unresolved action; never repeat a
destructive action automatically. Open/reveal are non-mutating and need no
durable Trash intent. Grant expiry does not prove a pending native move stopped.

## Required future contract tests

Fragmented/multiple UTF-8 frames; invalid types/JSON/oversize; handshake version
mismatch; request correlation/idempotency/conflicts; snapshot paging concurrent
with progress; stale attempt events; slow consumer; shutdown/crash mid-transfer;
no automatic destructive replay; None profile forwarding; private auth failures;
optional processing warnings; sanitized secrets/headers/URLs; verified file grants
and symlink/out-of-root rejection. Run Python and Swift decoders against the same
sanitized fixtures before a native feature depends on this protocol.
