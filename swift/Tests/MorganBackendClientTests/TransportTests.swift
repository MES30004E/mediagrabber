import Foundation
import XCTest
@testable import MorganBackendClient

private final class TransportCapture: @unchecked Sendable {
    private let lock = NSLock()
    private var bytes = Data()
    func append(_ chunk: Data) -> Data {
        lock.lock(); defer { lock.unlock() }
        bytes.append(chunk)
        return bytes
    }
}

final class TransportTests: XCTestCase {
    // A JSONL peer stays alive between commands. Waiting to fill a read buffer
    // (or for EOF) must not conceal its small, already flushed response.
    func testSmallFlushedStdoutArrivesBeforeWorkerExit() async throws {
        let python = ProcessInfo.processInfo.environment["MORGAN_TEST_PYTHON"] ?? "/usr/bin/python3"
        let fixture = try XCTUnwrap(Bundle.module.url(forResource: "bridge_worker", withExtension: "py", subdirectory: "Fixtures"))
        let received = expectation(description: "Small stdout frame delivered while worker remains alive")
        let output = TransportCapture()
        let expected = Data("small frame\n".utf8)
        let transport = WorkerTransport(
            configuration: WorkerConfiguration(executable: URL(fileURLWithPath: python),
                                               arguments: [fixture.path, "small-output"]),
            receive: { bytes, error, done in
                defer { done() }
                XCTAssertNil(error)
                if let bytes {
                    let collected = output.append(bytes)
                    if collected.count >= expected.count {
                        XCTAssertEqual(collected, expected)
                        received.fulfill()
                    }
                }
            }, exited: { _ in })
        try transport.launch()
        defer { transport.terminate() }
        await fulfillment(of: [received], timeout: 2)
        XCTAssertNil(transport.statusIfExited)
    }
}
