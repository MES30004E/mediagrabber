import Foundation
import XCTest
@testable import MorganBackendClient

final class ProtocolTests: XCTestCase {
    static var repository: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    }
    func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: Self.repository.appendingPathComponent("tests/protocol_fixtures/\(name).json"))
    }
    func testExactPythonGoldenRequests() throws {
        let decoder = JSONDecoder()
        let hello = try decoder.decode(BackendCommand.self, from: fixture("hello.request"))
        XCTAssertEqual(hello.type, .hello)
        for (name, input) in [("analyse-url", "https://www.youtube.com/watch?v=fixture"),
                              ("analyse-search", "example artist song"), ("analyse-watch-later", ":ytwatchlater")] {
            let command = try decoder.decode(BackendCommand.self, from: fixture("\(name).request"))
            XCTAssertEqual(command.type, .analyse)
            guard case .analyse(let payload) = command.payload else { return XCTFail("Wrong payload") }
            XCTAssertEqual(payload.inputs, [input])
            let encoded = try JSONEncoder().encode(command)
            let again = try decoder.decode(BackendCommand.self, from: encoded)
            XCTAssertEqual(again.requestID, command.requestID)
            XCTAssertEqual(again.sessionID, command.sessionID)
        }
    }
    func testExactPythonGoldenMessages() throws {
        for name in ["hello.response", "ready.event", "analysis-item.event", "download-progress.event", "error.event"] {
            let message = try BackendMessage.decode(fixture(name))
            XCTAssertEqual(message.protocolVersion, "1.0")
            XCTAssertGreaterThan(message.sequence, 0)
        }
        let item = try BackendMessage.decode(fixture("analysis-item.event"))
        guard case .analysisItem(let payload) = item.payload else { return XCTFail("Wrong item") }
        XCTAssertEqual(payload.item.title, "Example video")
        XCTAssertEqual(payload.item.sourceID, item.sourceID)
        let error = try BackendMessage.decode(fixture("error.event"))
        XCTAssertEqual(error.operationError, .protocolError("protocol.invalid_json"))
    }
    func mutated(_ changes: [String: Any], removing: String? = nil) throws -> Data {
        var value = try XCTUnwrap(JSONSerialization.jsonObject(with: fixture("ready.event")) as? [String: Any])
        changes.forEach { value[$0.key] = $0.value }
        if let key = removing { value.removeValue(forKey: key) }
        return try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    }
    func testStrictEnvelopeAndUnknownEvent() throws {
        XCTAssertThrowsError(try BackendMessage.decode(mutated([:], removing: "job_id")))
        XCTAssertThrowsError(try BackendMessage.decode(mutated(["request_id": "bad"])))
        XCTAssertThrowsError(try BackendMessage.decode(mutated(["sequence": true])))
        XCTAssertThrowsError(try BackendMessage.decode(mutated(["protocol_version": "2.0"]))) { error in
            XCTAssertEqual(error as? BackendError, .incompatibleProtocolVersion)
        }
        let message = try BackendMessage.decode(mutated(["type": "future.event", "payload": ["secret": "discarded"]]))
        XCTAssertEqual(message.eventType, .unknown("future.event"))
        guard case .unknown = message.payload else { return XCTFail("Unknown payload retained") }
        XCTAssertNoThrow(try BackendMessage.decode(mutated([:]))) // ordering independent
    }
    func testMalformedJSONAndSafeErrors() {
        XCTAssertThrowsError(try BackendMessage.decode(Data("{cookie=private}".utf8))) { error in
            XCTAssertEqual(error as? BackendError, .malformedFrame)
            XCTAssertFalse(String(describing: error).contains("private"))
        }
    }
    func testFragmentedUTF8CRLFAndMultipleFrames() throws {
        var framer = JSONLineFramer(maximumBytes: 32)
        let bytes = Array("{\"title\":\"é\"}\r\n{}\n".utf8)
        var frames: [FrameResult] = []
        for byte in bytes { frames += framer.append(Data([byte])) }
        XCTAssertEqual(frames, [.frame(Data("{\"title\":\"é\"}".utf8)), .frame(Data("{}".utf8))])
        XCTAssertNil(framer.finish())
    }
    func testFrameBoundaryOversizeRecoveryAndEOF() {
        var framer = JSONLineFramer(maximumBytes: 4)
        XCTAssertEqual(framer.append(Data("1234\r\n".utf8)), [.frame(Data("1234".utf8))])
        XCTAssertEqual(framer.append(Data("12345678".utf8)), [.failure(.oversizedFrame)])
        XCTAssertEqual(framer.append(Data("9\n{}\n".utf8)), [.frame(Data("{}".utf8))])
        _ = framer.append(Data("{".utf8))
        XCTAssertEqual(framer.finish(), .malformedFrame)
    }
}

extension ProtocolTests {
    func testDownloadStartedUsesActualIntegerFormatCount() throws {
        let message = try BackendMessage.decode(mutated([
            "type": "download.started", "request_id": "00000000-0000-4000-8000-000000000003",
            "job_id": "00000000-0000-4000-8000-000000000005", "job_revision": 1,
            "attempt_id": "00000000-0000-4000-8000-000000000006",
            "payload": ["runtime_version": "fixture", "formats_playable": 2]
        ]))
        guard case .downloadStarted(let p) = message.payload else { return XCTFail("Wrong payload") }
        XCTAssertEqual(p.formatsPlayable, 2)
    }
    func testUnknownEventStillRequiresObjectPayload() throws {
        XCTAssertThrowsError(try BackendMessage.decode(mutated(["type": "future.event", "payload": []])))
        XCTAssertThrowsError(try BackendMessage.decode(mutated(["type": "future.event", "payload": NSNull()])))
    }
}
