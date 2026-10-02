# Backend worker — Phase 1

The Python/Qt application remains the behavioral reference and uses its unchanged
in-process backend. The independent worker shares production parsing, auth policy,
analyse_with_authentication/analyse_target, download_job and RuntimeSnapshot types.
It imports no Qt widgets/tasks and does not touch Qt settings, history or runtime
metadata. The Phase 2 Swift client is documented in SWIFT_BACKEND_CLIENT.md; no local Xcode/admin requirement is introduced.

## Run and framing

From the repository root:

```sh
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.backend
```

Use the process's private stdin/stdout pipes. Each frame is one UTF-8 JSON object
and LF, ≤1 MiB of JSON bytes excluding LF/CRLF. Always read stdout concurrently with sending commands; stderr is
reserved for safe transport/debug diagnostics, not an API. Dependency stdout and
stderr text is discarded at both Python and OS descriptor levels, including
inherited child-process output; structured diagnostics carry category/level.
Protocol writes use a private non-inheritable duplicate of the stdout pipe.
Never parse terminal progress. Startup performs no network/health/update request.

An offline hello/EOF smoke (no operation starts):

```sh
PYTHONPATH=src .venv/bin/python -m morgan_media_downloader.backend <<'JSONL'
{"protocol_version":"1.0","kind":"command","type":"session.hello","request_id":"00000000-0000-4000-8000-000000000001","session_id":null,"job_id":null,"source_id":null,"timestamp":"2026-10-01T12:00:00Z","payload":{"supported_versions":["1.0"]}}
JSONL
```

Expect a completed hello response and session.ready event, then exit 0 on EOF.
Take session_id from that response for subsequent commands in a still-open
process. Each new command uses a new UUID request_id and UTC RFC3339 timestamp.
Golden files in tests/protocol_fixtures/ show the shapes with synthetic IDs;
substitute live worker session/source IDs rather than replaying example IDs.

## Commands and operation ownership

- session.hello / session.ping: capabilities and liveness.
- analysis.start: inputs, purpose preview, optional config; structured item IDs.
- jobs.enqueue: completed analysis_request_id, selected source_ids, options with
  download_dir, optional config override. The worker creates job/attempt UUIDs.
- analysis.cancel: target_request_id. jobs.cancel: job_id plus last observed
  expected_job_revision. A stale revision rejects with state.conflict.
- session.shutdown: request stop on active work, join owned threads, then respond.

The worker limits concurrent operations to four. Source IDs belong to successful
analysis in this session. Reusing a request UUID does not rerun work; retained
responses replay, expired cached responses reject. Sources and jobs are
in-memory, not durable queue state. EOF requests cancellation and waits for
threads. There is no automatic resume, restart, deletion or replay on crash.
Never run Qt/worker transfers concurrently to the same output paths.

Analysis uses the existing text-search default (ytsearch10), exact :ytwatchlater,
Watch Later aliases, playlist expansion, auth retry policy and routing/provider
arguments. Cancellation sets a per-operation threading.Event: analysis checks
between extraction calls/items; download_job checks its existing progress hooks.
Analysis calls and ffmpeg/postprocessing may not stop until they return. No force
termination or stronger cancellation is claimed. Terminal cancellation events
are emitted after worker exit; partial/generated output is retained.

## Configuration and privacy

Config carries auth mode, browser/profile selection, cookie-file path reference,
provider URL/home, and proxy mode/host/port. Cookie-file contents, Keychain
passwords, raw browser cookies and credential-bearing proxy URLs never cross IPC.
The worker leaves cookie extraction to supported yt-dlp options. Provider URLs
must be HTTP(S), without userinfo/query credentials. Password-bearing proxies and
Managed Tor ownership are unsupported; the existing Qt paths remain available.

Per-operation bundled runtime snapshots are used; no verified user-runtime
activation or automatic update runs. Download options are explicitly allowlisted;
absolute/parent-traversing filename templates fail validation. Existing Qt
configuration and behavior are not changed by these new command restrictions.
Existing pinned-provider discovery/import compatibility runs once under a lock
when the first runtime is needed; it performs no provider network probe.

Wire adapters are separate from application dataclasses. They omit request
headers, signed thumbnail URLs and config paths. Display URLs omit credentials,
query and fragment; they are for presentation, not future extraction. Source IDs
retain worker-side extraction inputs. Metadata/warnings are redacted and bounded;
errors use fixed safe messages, not raw tracebacks. Final output paths remain
private local result fields. IPC streams must not be published or uploaded.

## Validation

```sh
.venv/bin/python -m pytest -q tests/test_backend_protocol.py tests/test_backend_service.py tests/test_backend_worker.py tests/test_backend_fixtures.py
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m pip check
```

Use fresh MORGAN_DATA_DIR/MORGAN_LOG_DIR/MORGAN_CACHE_DIR for full-suite runs as
documented in CODEX_CONTEXT.md. Tests use the real production logic with a fake
external yt-dlp boundary; no live accounts or cookies. The subprocess test harness
is tests/backend_subprocess_fixture.py, never a production fake/test-mode flag.
Golden fixtures independently pin wire fields for later Swift tests.

Verification after review: 58 targeted backend tests, full suite 280 passed
(no skipped/expected failures), dependency check passed. Regression cases
include provider imports without network, nested JSON recovery, semantic request
ID reuse and native/inherited subprocess output suppression. CI's full Python job
discovers these tests; branch trigger includes migration/backend-protocol. Phase 2 adds required hosted Swift build/tests and real worker interoperability;
see SWIFT_BACKEND_CLIENT.md for the native validation boundary.

## Deferred capabilities

Durable queue/database ownership, snapshots/reconnect, restart/resume/Trash,
native Keychain integration, runtime updates, owned Tor, torrent and converter
commands are not advertised. Typed error taxonomy/verification payloads are a
minimal Phase 1 subset, not complete native UX. Output writes are synchronous;
a non-reading parent can block events, cancellation and shutdown. Progress
coalescing/output-stall watchdog and stronger engine cancellation need separate
qualification before a production native frontend relies on this worker.
