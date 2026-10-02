# Swift Backend Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement and publish Phase 2's Foundation-only Swift client for the existing Python JSONL worker, qualified through hosted macOS CI.

**Architecture:** One actor owns the worker session, request continuations, lifecycle and event stream. Independent serial I/O queues drain stdout/stderr and serialize writes without blocking the Swift executor. Explicit Codable payloads and a bounded incremental byte framer share the existing Python golden fixtures.

**Tech Stack:** SwiftPM (Swift tools 5.9, macOS 12), Foundation, XCTest, Python 3.12, GitHub Actions macos-15.

**Spec:** Approved docs/SWIFT_ARCHITECTURE.md, executable Phase 1 subset in docs/BACKEND_PROTOCOL.md, and the user's Phase 2 brief of 2 October 2026. Latest brief excludes SwiftUI and state snapshots from this phase.

## Global Constraints

- Base e02d3dce732de62637c319a7673f4080b05f6a0c; branch migration/swift-bridge; push without force; no merge.
- Foundation only; no UI, duplicate extraction engines, Qt rewiring, signing, credentials or local Xcode.
- Exact canonical Phase 1 commands/events; protocol 1.0; 1048576 JSON bytes excluding LF/CRLF.
- Tests load tests/protocol_fixtures directly; no copied or newly generated incompatible fixtures.
- Native success requires observed hosted macOS build/test results; Linux Python results are separate.

## Review Focus

- Split UTF-8 and CRLF, multiple frames and oversized unterminated input must remain bounded and recover deterministically.
- Pipe flood and non-reading worker must not block the actor or leave writes/pending requests forever.
- Response/event before registration, wrong UUID/type/session and late response after cancellation must not resume the wrong request.
- Exit notification racing final stdout must preserve shutdown response before resolving lifecycle and fail all remaining waiters.
- Unknown events and untrusted stderr/errors must not expose raw traffic through public error descriptions or logs.

## Task 1: Protocol and framing

Files: swift/Package.swift; Sources/MorganBackendClient/{Protocol,Payloads,BackendError,JSONLineFramer}.swift; Tests/MorganBackendClientTests/ProtocolTests.swift; scripts/check_backend_protocol.py; tests/test_swift_protocol_contract.py.
Interfaces: BackendCommand Codable; BackendMessage Decodable; ProtocolContract version/frame limit/identifier enums; JSONLineFramer.append(Data) -> [FrameResult].
- [ ] Add tests for exact nine fixtures, reordered fields, missing nullable envelope keys, invalid UUID/version/types, unknown event, malformed JSON, split UTF-8/CRLF, size boundary and recovery; add Python drift-check failing test.
- [ ] Observe missing-package/contract failures; implement explicit payload decoding and bounded framing without raw-error strings.
- [ ] Run hosted protocol tests and Python drift test; commit deliverable.

## Task 2: Worker process client

Files: Sources/MorganBackendClient/{WorkerTransport,BackendClient}.swift; Tests/MorganBackendClientTests/{ClientTests,WorkerIntegrationTests}.swift; Tests/MorganBackendClientTests/Fixtures/bridge_worker.py.
Interfaces: BackendClient.start(configuration), send(command) -> BackendMessage, events stream, lifecycle(), shutdown(); WorkerConfiguration executable/arguments/workingDirectory/environment/timeouts.
- [ ] Test actual worker hello/ping/shutdown, real deterministic Watch Later fixture, separate stderr flood, crash/EOF, timeout, cancellation, response and event correlation, session/sequence checks, graceful exit.
- [ ] Observe failure before transport/client implementation on hosted CI; implement independent owned process I/O queues and actor correlation with bounded outstanding/stream state.
- [ ] Run hosted whole Swift suite and real worker integration; commit deliverable.

## Task 3: CI and qualification

Files: .github/workflows/migration-validation.yml; docs/{SWIFT_BACKEND_CLIENT,SWIFT_ARCHITECTURE,BACKEND_PROTOCOL,MIGRATION_PHASES,NATIVE_CI_DESIGN}.md; .gitignore.
- [ ] Add branch trigger and macOS Python wheel setup; run deterministic drift check, Python backend tests, Swift build and entire nonzero Swift tests with actual worker integration required.
- [ ] Document lifecycle, framing, concurrency, errors, credential boundary and ephemeral limitations; keep future design distinguishable from implementation.
- [ ] Run targeted/full Python suite, pip check, YAML/shell validation and diff checks.
- [ ] Obtain one fresh whole-branch review; fix Important findings with regressions; record rulings and deferred minors.
- [ ] Commit/push; match remote SHA; observe hosted Actions outcome or report concrete access blocker without claiming Swift success.
