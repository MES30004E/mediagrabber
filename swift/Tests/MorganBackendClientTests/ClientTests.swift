import Foundation
import XCTest
@testable import MorganBackendClient

final class ClientTests: XCTestCase {
    func configuration(_ mode: String, timeout: TimeInterval = 3) throws -> WorkerConfiguration {
        let python = ProcessInfo.processInfo.environment["MORGAN_TEST_PYTHON"] ?? "/usr/bin/python3"
        let fixture = try XCTUnwrap(Bundle.module.url(forResource: "bridge_worker", withExtension: "py", subdirectory: "Fixtures"))
        return WorkerConfiguration(executable: URL(fileURLWithPath: python), arguments: [fixture.path, mode],
                                   requestTimeout: timeout, shutdownTimeout: 2)
    }
    func testHandshakePingGracefulShutdown() async throws {
        let client = BackendClient()
        let capabilities = try await client.start(configuration("normal"))
        XCTAssertEqual(capabilities.selectedVersion, "1.0")
        let state = await client.lifecycle()
        XCTAssertEqual(state, .ready)
        let response = try await client.send(.ping)
        XCTAssertEqual(response.type, "session.ping")
        XCTAssertNotNil(response.requestID)
        try await client.shutdown()
        let stopped = await client.lifecycle()
        XCTAssertEqual(stopped, .stopped)
    }
    func testStderrFloodDoesNotBlockOrBecomeProtocol() async throws {
        let client = BackendClient()
        _ = try await client.start(configuration("stderr-flood"))
        let response = try await client.send(.ping)
        XCTAssertEqual(response.type, "session.ping")
        try await client.shutdown()
    }
    func testUnknownEventIsSafeAndCorrelated() async throws {
        let client = BackendClient()
        let events = client.events
        let collected = Task { () throws -> BackendMessage in
            for try await message in events {
                if message.eventType == .unknown("future.event") { return message }
            }
            throw BackendError.workerEOF
        }
        _ = try await client.start(configuration("unknown"))
        let response = try await client.send(.ping)
        let unknown = try await collected.value
        XCTAssertEqual(unknown.requestID, response.requestID)
        guard case .unknown = unknown.payload else { return XCTFail("Unknown data retained") }
        try await client.shutdown()
    }
    func testMalformedWorkerOutputFailsSafely() async throws {
        let client = BackendClient()
        _ = try await client.start(configuration("malformed"))
        do { _ = try await client.send(.ping); XCTFail("Expected malformed frame") }
        catch { XCTAssertEqual(error as? BackendError, .malformedFrame) }
        await client.abort()
    }
    func testCorrelationRejectsWrongIDTypeSessionAndEvent() async throws {
        for mode in ["wrong-id", "wrong-type", "wrong-session", "event-wrong-type"] {
            let client = BackendClient()
            _ = try await client.start(configuration(mode))
            do { _ = try await client.send(.ping); XCTFail("Expected correlation failure: \(mode)") }
            catch { XCTAssertEqual(error as? BackendError, .correlationFailure) }
            await client.abort()
        }
    }
    func testEarlyEOFAndCrashAreDistinct() async throws {
        for (mode, expected) in [("eof", BackendError.workerEOF), ("crash", BackendError.workerCrash(7))] {
            let client = BackendClient()
            do { _ = try await client.start(configuration(mode)); XCTFail("Expected termination") }
            catch { XCTAssertEqual(error as? BackendError, expected) }
            await client.abort()
        }
    }
    func testTimeoutReleasesRequestAndOwnedWorker() async throws {
        let client = BackendClient()
        _ = try await client.start(configuration("timeout", timeout: 0.3))
        do { _ = try await client.send(.ping); XCTFail("Expected timeout") }
        catch { XCTAssertEqual(error as? BackendError, .timeout) }
        try await client.shutdown()
    }
    func testCancelledWaitDoesNotReplayOrCorruptLaterResponse() async throws {
        let client = BackendClient()
        _ = try await client.start(configuration("delay"))
        let probeStart = ProcessInfo.processInfo.systemUptime
        let request = Task {
            let response = try await client.send(.ping)
            print("Cancellation ordering probe: response completed after \(ProcessInfo.processInfo.systemUptime - probeStart)s")
            return response
        }
        try await Task.sleep(nanoseconds: 30_000_000)
        print("Cancellation ordering probe: cancel invoked after \(ProcessInfo.processInfo.systemUptime - probeStart)s")
        request.cancel()
        do { _ = try await request.value; XCTFail("Expected cancellation") }
        catch { XCTAssertEqual(error as? BackendError, .cancelled) }
        let next = try await client.send(.ping)
        XCTAssertEqual(next.type, "session.ping")
        try await client.shutdown()
    }
    func testNonreadingWorkerCannotBlockHandshakeForever() async throws {
        let client = BackendClient()
        do { _ = try await client.start(configuration("no-read", timeout: 0.2)); XCTFail("Expected timeout") }
        catch { XCTAssertEqual(error as? BackendError, .timeout) }
        await client.abort()
    }
    func testPartialFrameAtEOFIsMalformed() async throws {
        let client = BackendClient()
        _ = try await client.start(configuration("partial"))
        do { _ = try await client.send(.ping); XCTFail("Expected incomplete frame") }
        catch { XCTAssertEqual(error as? BackendError, .malformedFrame) }
        await client.abort()
    }
}


extension ClientTests {
    func testGracefulExitImmediatelyFailsOutstandingRequest() async throws {
        let client = BackendClient()
        defer { Task { await client.abort() } }
        let events = client.events
        let observed = Task {
            for try await event in events {
                if case .diagnostic(let p) = event.payload, p.safeMessage == "ping received" { return }
            }
            throw BackendError.workerEOF
        }
        _ = try await client.start(configuration("pending-on-shutdown", timeout: 5))
        let ping = Task { try await client.send(.ping) }
        try await observed.value
        try await client.shutdown()
        let start = Date()
        do { _ = try await ping.value; XCTFail("Outstanding ping must fail at exit") }
        catch { XCTAssertEqual(error as? BackendError, .workerEOF) }
        XCTAssertLessThan(Date().timeIntervalSince(start), 1)
    }
    func testCancellationAfterShutdownAcknowledgementReleasesWaiter() async throws {
        let client = BackendClient()
        defer { Task { await client.abort() } }
        let events = client.events
        let observed = Task {
            for try await event in events {
                if case .diagnostic(let p) = event.payload, p.safeMessage == "shutdown acknowledged" { return }
            }
            throw BackendError.workerEOF
        }
        _ = try await client.start(configuration("shutdown-hang"))
        let shutdown = Task { try await client.shutdown() }
        try await observed.value
        let start = Date()
        shutdown.cancel()
        do { try await shutdown.value; XCTFail("Shutdown wait must cancel") }
        catch { XCTAssertEqual(error as? BackendError, .cancelled) }
        XCTAssertLessThan(Date().timeIntervalSince(start), 1)
    }
}


extension ClientTests {
    func testEOFWithoutProcessExitFailsAndStopsOwnership() async throws {
        let client = BackendClient()
        defer { Task { await client.abort() } }
        _ = try await client.start(configuration("close-stdout"))
        let start = Date()
        do { _ = try await client.send(.ping); XCTFail("Closed output must be unavailable") }
        catch { XCTAssertEqual(error as? BackendError, .workerEOF) }
        XCTAssertLessThan(Date().timeIntervalSince(start), 1)
        let state = await client.lifecycle()
        XCTAssertEqual(state, .failed(.workerEOF))
    }
    func testCancellationDuringFullPipeInvalidatesPartialFrame() async throws {
        let client = BackendClient()
        defer { Task { await client.abort() } }
        let events = client.events
        let observed = Task {
            for try await event in events {
                if case .diagnostic(let p) = event.payload, p.safeMessage == "will not read" { return }
            }
            throw BackendError.workerEOF
        }
        _ = try await client.start(configuration("fill-stdin"))
        try await observed.value
        let inputs = Array(repeating: String(repeating: "x", count: 40000), count: 20)
        let request = Task { try await client.send(.analyse(AnalysePayload(inputs: inputs))) }
        try await Task.sleep(nanoseconds: 100_000_000)
        request.cancel()
        do { _ = try await request.value; XCTFail("Expected cancelled wait") }
        catch { XCTAssertEqual(error as? BackendError, .cancelled) }
        try await Task.sleep(nanoseconds: 200_000_000)
        let state = await client.lifecycle()
        XCTAssertEqual(state, .failed(.transportFailure))
    }
}
