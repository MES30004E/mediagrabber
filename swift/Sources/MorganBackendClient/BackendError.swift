import Foundation

/// Deliberately carries no raw JSON, stderr, paths, input URLs or exception text.
public enum BackendError: Error, Sendable, Equatable, CustomStringConvertible {
    case incompatibleProtocolVersion
    case malformedFrame
    case oversizedFrame
    case workerEOF
    case workerCrash(Int32)
    case protocolError(String)
    case operationFailed(String)
    case authenticationRequired
    case correlationFailure
    case timeout
    case cancelled
    case invalidLifecycle
    case transportFailure
    case consumerTooSlow
    case capacityExceeded

    public var description: String {
        switch self {
        case .incompatibleProtocolVersion: return "Backend protocol version is incompatible."
        case .malformedFrame: return "Malformed backend frame."
        case .oversizedFrame: return "Backend frame exceeds the byte limit."
        case .workerEOF: return "Backend output closed unexpectedly."
        case .workerCrash: return "Backend worker terminated unexpectedly."
        case .protocolError: return "Backend rejected the protocol request."
        case .operationFailed: return "Backend operation failed."
        case .authenticationRequired: return "Backend authentication is required."
        case .correlationFailure: return "Backend request correlation failed."
        case .timeout: return "Backend request timed out."
        case .cancelled: return "Backend request was cancelled."
        case .invalidLifecycle: return "Backend is unavailable for this request."
        case .transportFailure: return "Backend transport failed."
        case .consumerTooSlow: return "Backend event consumer could not keep up."
        case .capacityExceeded: return "Backend client request capacity exceeded."
        }
    }
}
