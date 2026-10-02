import Foundation
import XCTest
@testable import MorganBackendClient

final class WorkerIntegrationTests: XCTestCase {
    func configuration(mockBoundary: Bool = false) throws -> WorkerConfiguration {
        let root = ProtocolTests.repository
        let python = try XCTUnwrap(ProcessInfo.processInfo.environment["MORGAN_TEST_PYTHON"],
                                  "Hosted CI must provide the installed Python executable; integration must not skip.")
        var environment = ProcessInfo.processInfo.environment
        environment["PYTHONPATH"] = root.appendingPathComponent("src").path
        let arguments = mockBoundary ? [root.appendingPathComponent("tests/backend_subprocess_fixture.py").path] :
                                      ["-m", "morgan_media_downloader.backend"]
        return WorkerConfiguration(executable: URL(fileURLWithPath: python), arguments: arguments,
                                   workingDirectory: root, environment: environment)
    }
    func testActualPythonWorkerHelloPingShutdown() async throws {
        let client = BackendClient()
        let hello = try await client.start(configuration())
        XCTAssertFalse(hello.durableJobs)
        XCTAssertFalse(hello.secretIPC)
        XCTAssertEqual(hello.maxFrameBytes, ProtocolContract.maximumFrameBytes)
        XCTAssertEqual(Set(hello.capabilities), Set(CommandType.allCases.map(\.rawValue)))
        _ = try await client.send(.ping)
        try await client.shutdown()
        let state = await client.lifecycle()
        XCTAssertEqual(state, .stopped)
    }
    func testRealWorkerDeterministicWatchLaterAnalysis() async throws {
        let client = BackendClient()
        let events = client.events
        let collected = Task { () throws -> [BackendMessage] in
            var messages: [BackendMessage] = []
            for try await message in events {
                if message.type.hasPrefix("analysis.") {
                    messages.append(message)
                    if message.eventType == .analysisCompleted { return messages }
                }
            }
            throw BackendError.workerEOF
        }
        _ = try await client.start(configuration(mockBoundary: true))
        let response = try await client.send(.analyse(AnalysePayload(inputs: [":ytwatchlater"])))
        let messages = try await collected.value
        XCTAssertEqual(messages.map(\.type), ["analysis.started", "analysis.item", "analysis.completed"])
        XCTAssertTrue(messages.allSatisfy { $0.requestID == response.requestID })
        guard case .analysisItem(let payload) = messages[1].payload else { return XCTFail("No item") }
        XCTAssertFalse(payload.item.title.contains("private-value"))
        XCTAssertEqual(payload.item.displayURL, "https://youtube.test/watch")
        try await client.shutdown()
    }
}
