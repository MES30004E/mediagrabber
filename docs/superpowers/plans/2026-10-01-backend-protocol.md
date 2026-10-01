# Backend Protocol Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Expose the retained Python analysis/download behavior through a tested local worker without changing Qt.

**Architecture:** A strict versioned command schema, explicit DTO adapters, and a bounded in-memory service sit behind a JSONL process entry point. Existing downloader/auth/parsing/runtime snapshot types remain the engines; the Qt app keeps its in-process path. Persistent queue/reconnect, native secrets, Tor ownership and native UI are deferred and not advertised.

**Tech Stack:** Python 3.12, stdlib dataclasses/threading/JSON, existing yt-dlp API, pytest.

**Spec:** docs/BACKEND_PROTOCOL.md and the user's Phase 1 brief.

## Global Constraints

- Protocol version 1.0; JSONL over local stdin/stdout; stdout contains only protocol frames.
- Maximum frame 1 MiB; request/session/job/source identity uses UUIDs.
- Do NOT send Keychain secrets or raw browser cookie contents over the protocol.
- Preserve Python/PySide6 and all existing engines; no Swift, Xcode, signing or notarisation.
- Keep current Qt application on the existing in-process path.
- Branch migration/backend-protocol from published design commit 40552ae.

## Review Focus

- Wrong session/reused request IDs must not launch duplicate downloads.
- Missing/invalid types and secret-bearing proxy URLs must fail before engine work.
- Cancellation racing completion must not emit two terminal outcomes.
- Oversized/invalid UTF-8 frames must not contaminate stdout or crash the parser.
- Library output, cookie paths and signed URLs must not leak through events/errors.

## Task 1: Wire models and adapters

**Files:** backend/protocol.py, backend/adapters.py, tests/test_backend_protocol.py.
**Interfaces:** parse_command(raw: bytes) -> Command; media_payload(MediaItem, source_id) -> dict; progress_payload(DownloadJob) -> dict; options_from_payload(dict) -> DownloadOptions.
- [x] Write tests for strict envelopes, types/IDs/version, unknown commands, options and redacted explicit serialization.
- [x] Run `.venv/bin/python -m pytest -q tests/test_backend_protocol.py`; observe missing-module failure.
- [x] Implement typed command/payload models and allowlisted wire adapters; rerun targeted tests.
- [x] Commit the tested models/adapters.

## Task 2: Operation service

**Files:** backend/service.py, tests/test_backend_service.py.
**Interfaces:** BackendService(emit, runtime_factory=None); handle(Command) -> bool; close() -> None; wait_idle(timeout) -> bool. Emit accepts kind/type/request/job/source/payload/revision/attempt.
- [x] Write tests for handshake, real analysis chain with fake yt-dlp boundary, search/WL/private routing, enqueue/download callbacks and request/job cancellation.
- [x] Observe missing service failure, then implement service using existing production functions.
- [x] Test duplicate IDs/session rejection/cancellation races, errors and no startup network.
- [x] Commit the tested service.

## Task 3: Process/framing and fixtures

**Files:** backend/__init__.py, backend/__main__.py, backend/worker.py; tests/test_backend_worker.py; tests/protocol_fixtures/.
**Interfaces:** worker.run(input_stream, output_stream) -> int; worker.main() -> int. Binary input/output permit bounded UTF-8 framing.
- [x] Write subprocess tests for hello/EOF/shutdown/errors, fragmented framing, oversize/invalid UTF-8, deterministic analysis harness and stdout isolation.
- [x] Observe missing entry-point failure, implement reader/writer and process entry point, rerun tests.
- [x] Add representative fixed-ID golden requests/events with explicit provenance and validate them.
- [x] Commit the tested transport/fixtures.

## Task 4: Documentation and whole-branch validation

**Files:** docs/BACKEND_PROTOCOL.md, SWIFT_ARCHITECTURE.md, MIGRATION_PHASES.md, BACKEND_WORKER.md; CI only if needed.
- [x] Record canonical Phase 1 commands/capabilities, ephemeral state, cancellation limits and no-secret configuration changes.
- [x] Run targeted backend tests, full Python suite, pip check and real-process smoke with exact results.
- [x] Check Qt startup/shutdown on fresh offscreen state and unchanged existing paths.
- [x] Obtain fresh whole-branch review; fix meaningful findings with failing tests then the full suite.
- [x] Commit review fixes/docs; show baseline diff and clean Git state. Do not merge or begin Phase 2.
