import Foundation

public enum FrameResult: Equatable, Sendable {
    case frame(Data)
    case failure(BackendError)
}

/// Bounds retained bytes even before a newline arrives. A trailing CR is framing,
/// only when followed by LF. After oversize, discard through LF then recover.
public struct JSONLineFramer: Sendable {
    private let maximumBytes: Int
    private var buffer = Data()
    private var discarding = false
    public init(maximumBytes: Int = ProtocolContract.maximumFrameBytes) {
        precondition(maximumBytes > 0)
        self.maximumBytes = maximumBytes
    }
    public mutating func append(_ data: Data) -> [FrameResult] {
        var result: [FrameResult] = []
        for byte in data {
            if discarding {
                if byte == 10 { discarding = false }
                continue
            }
            if byte == 10 {
                if buffer.last == 13 { buffer.removeLast() }
                result.append(.frame(buffer))
                buffer.removeAll(keepingCapacity: true)
            } else {
                buffer.append(byte)
                if buffer.count > maximumBytes && !(buffer.count == maximumBytes + 1 && byte == 13) {
                    result.append(.failure(.oversizedFrame))
                    buffer.removeAll(keepingCapacity: true)
                    discarding = true
                }
            }
        }
        return result
    }
    public mutating func finish() -> BackendError? {
        defer { buffer.removeAll(); discarding = false }
        return buffer.isEmpty ? nil : .malformedFrame
    }
}
