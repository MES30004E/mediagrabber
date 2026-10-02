import Foundation

public enum ProtocolContract {
    public static let version = "1.0"
    public static let maximumFrameBytes = 1048576
}
public enum CommandType: String, Codable, CaseIterable, Sendable {
    case hello = "session.hello"
    case analyse = "analysis.start"
    case enqueue = "jobs.enqueue"
    case cancelAnalysis = "analysis.cancel"
    case cancelJob = "jobs.cancel"
    case ping = "session.ping"
    case shutdown = "session.shutdown"
}
public enum EventType: Equatable, Sendable {
    case ready, analysisStarted, analysisItem, analysisCompleted, analysisFailed, analysisCancelled
    case downloadStarted, downloadProgress, downloadProcessing, downloadCompleted, downloadFailed
    case jobCancelled, authRequired, authFailed, diagnostic, error
    case unknown(String)
    public init(identifier: String) {
        switch identifier {
        case "session.ready": self = .ready
        case "analysis.started": self = .analysisStarted
        case "analysis.item": self = .analysisItem
        case "analysis.completed": self = .analysisCompleted
        case "analysis.failed": self = .analysisFailed
        case "analysis.cancelled": self = .analysisCancelled
        case "download.started": self = .downloadStarted
        case "download.progress": self = .downloadProgress
        case "download.processing": self = .downloadProcessing
        case "download.completed": self = .downloadCompleted
        case "download.failed": self = .downloadFailed
        case "job.cancelled": self = .jobCancelled
        case "auth.required": self = .authRequired
        case "auth.failed": self = .authFailed
        case "diagnostic": self = .diagnostic
        case "error": self = .error
        default: self = .unknown(identifier)
        }
    }
    var terminal: Bool {
        switch self {
        case .analysisCompleted, .analysisFailed, .analysisCancelled, .downloadCompleted, .downloadFailed, .jobCancelled: return true
        default: return false
        }
    }
}
enum EnvelopeKey: String, CodingKey {
    case protocolVersion = "protocol_version", kind, type, requestID = "request_id", sessionID = "session_id"
    case jobID = "job_id", sourceID = "source_id", timestamp, payload, sequence, jobRevision = "job_revision", attemptID = "attempt_id"
}
extension KeyedDecodingContainer {
    func requiredNullable<T: Decodable>(_ type: T.Type, forKey key: Key) throws -> T? {
        guard contains(key) else { throw BackendError.malformedFrame }
        return try decodeIfPresent(type, forKey: key)
    }
}
func validateVersion(_ version: String) throws {
    guard version == ProtocolContract.version else { throw BackendError.incompatibleProtocolVersion }
}
func validateTimestamp(_ value: String) throws {
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    if formatter.date(from: value) != nil { return }
    formatter.formatOptions = [.withInternetDateTime]
    guard formatter.date(from: value) != nil else { throw BackendError.malformedFrame }
}
public enum CommandPayload: Sendable {
    case hello(HelloPayload), analyse(AnalysePayload), enqueue(EnqueuePayload)
    case cancelAnalysis(CancelAnalysisPayload), cancelJob(CancelJobPayload), ping, shutdown
    var type: CommandType {
        switch self {
        case .hello: return .hello; case .analyse: return .analyse; case .enqueue: return .enqueue
        case .cancelAnalysis: return .cancelAnalysis; case .cancelJob: return .cancelJob
        case .ping: return .ping; case .shutdown: return .shutdown
        }
    }
}
public struct BackendCommand: Codable, Sendable {
    public let protocolVersion: String
    public let requestID: UUID
    public let sessionID: UUID?
    public let jobID: UUID?
    public let sourceID: UUID?
    public let timestamp: String
    public let payload: CommandPayload
    public var type: CommandType { payload.type }
    public init(_ payload: CommandPayload, requestID: UUID = UUID(), sessionID: UUID? = nil, jobID: UUID? = nil) {
        self.protocolVersion = ProtocolContract.version; self.payload = payload
        self.requestID = requestID; self.sessionID = sessionID; self.jobID = jobID; self.sourceID = nil
        self.timestamp = ISO8601DateFormatter().string(from: Date())
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: EnvelopeKey.self)
        protocolVersion = try c.decode(String.self, forKey: .protocolVersion); try validateVersion(protocolVersion)
        guard try c.decode(String.self, forKey: .kind) == "command" else { throw BackendError.malformedFrame }
        let type = try c.decode(CommandType.self, forKey: .type)
        requestID = try c.decode(UUID.self, forKey: .requestID)
        sessionID = try c.requiredNullable(UUID.self, forKey: .sessionID)
        jobID = try c.requiredNullable(UUID.self, forKey: .jobID)
        sourceID = try c.requiredNullable(UUID.self, forKey: .sourceID)
        timestamp = try c.decode(String.self, forKey: .timestamp); try validateTimestamp(timestamp)
        switch type {
        case .hello: payload = .hello(try c.decode(HelloPayload.self, forKey: .payload))
        case .analyse: payload = .analyse(try c.decode(AnalysePayload.self, forKey: .payload))
        case .enqueue: payload = .enqueue(try c.decode(EnqueuePayload.self, forKey: .payload))
        case .cancelAnalysis: payload = .cancelAnalysis(try c.decode(CancelAnalysisPayload.self, forKey: .payload))
        case .cancelJob: payload = .cancelJob(try c.decode(CancelJobPayload.self, forKey: .payload))
        case .ping: _ = try c.decode(EmptyPayload.self, forKey: .payload); payload = .ping
        case .shutdown: _ = try c.decode(EmptyPayload.self, forKey: .payload); payload = .shutdown
        }
    }
    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: EnvelopeKey.self)
        try c.encode(protocolVersion, forKey: .protocolVersion); try c.encode("command", forKey: .kind)
        try c.encode(type, forKey: .type); try c.encode(requestID, forKey: .requestID)
        try c.encode(sessionID, forKey: .sessionID); try c.encode(jobID, forKey: .jobID); try c.encode(sourceID, forKey: .sourceID)
        try c.encode(timestamp, forKey: .timestamp)
        switch payload {
        case .hello(let p): try c.encode(p, forKey: .payload)
        case .analyse(let p): try c.encode(p, forKey: .payload)
        case .enqueue(let p): try c.encode(p, forKey: .payload)
        case .cancelAnalysis(let p): try c.encode(p, forKey: .payload)
        case .cancelJob(let p): try c.encode(p, forKey: .payload)
        case .ping, .shutdown: try c.encode(EmptyPayload(), forKey: .payload)
        }
    }
    public func framed() throws -> Data {
        var bytes = try JSONEncoder().encode(self)
        guard bytes.count <= ProtocolContract.maximumFrameBytes else { throw BackendError.oversizedFrame }
        bytes.append(10); return bytes
    }
}
public enum CommandResult: Sendable {
    case capabilities(Capabilities), operation(OperationAccepted), jobs(JobsAccepted), cancellation(CancellationAccepted), empty
}
public enum ResponseStatus: String, Codable, Sendable { case accepted, completed, rejected }
public struct BackendResponse: Sendable {
    public let status: ResponseStatus
    public let result: CommandResult?
    public let error: SafeBackendError?
    enum Key: String, CodingKey { case status, result, error }
    init(from decoder: Decoder, type: CommandType) throws {
        let c = try decoder.container(keyedBy: Key.self)
        status = try c.decode(ResponseStatus.self, forKey: .status)
        if status == .rejected {
            error = try c.decode(SafeBackendError.self, forKey: .error); result = nil; return
        }
        error = nil
        switch type {
        case .hello: result = .capabilities(try c.decode(Capabilities.self, forKey: .result))
        case .analyse: result = .operation(try c.decode(OperationAccepted.self, forKey: .result))
        case .enqueue: result = .jobs(try c.decode(JobsAccepted.self, forKey: .result))
        case .cancelAnalysis, .cancelJob: result = .cancellation(try c.decode(CancellationAccepted.self, forKey: .result))
        case .ping, .shutdown: _ = try c.decode(EmptyPayload.self, forKey: .result); result = .empty
        }
    }
}
public enum MessagePayload: Sendable {
    case response(BackendResponse), ready(Capabilities), analysisStarted(AnalysisStarted), analysisItem(AnalysisItem)
    case analysisCompleted(AnalysisCompleted), analysisCancelled, failure(ErrorPayload)
    case downloadStarted(DownloadStarted), progress(Progress), downloadCompleted(DownloadCompleted)
    case jobCancelled(JobCancelled), authRequired(AuthenticationRequired), diagnostic(Diagnostic), unknown
}
public struct BackendMessage: Decodable, Sendable {
    public let protocolVersion: String
    public let kind: String
    public let type: String
    public let requestID: UUID?
    public let sessionID: UUID
    public let jobID: UUID?
    public let sourceID: UUID?
    public let timestamp: String
    public let sequence: Int
    public let jobRevision: Int?
    public let attemptID: UUID?
    public let payload: MessagePayload
    public var eventType: EventType? { kind == "event" ? EventType(identifier: type) : nil }
    public var operationError: BackendError? {
        switch payload {
        case .failure(let p): return p.error.mapped
        case .response(let p): return p.error?.mapped
        case .authRequired: return .authenticationRequired
        default: return nil
        }
    }
    public static func decode(_ bytes: Data) throws -> Self {
        guard bytes.count <= ProtocolContract.maximumFrameBytes else { throw BackendError.oversizedFrame }
        do { return try JSONDecoder().decode(Self.self, from: bytes) }
        catch let error as BackendError { throw error }
        catch { throw BackendError.malformedFrame }
    }
    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: EnvelopeKey.self)
        protocolVersion = try c.decode(String.self, forKey: .protocolVersion); try validateVersion(protocolVersion)
        kind = try c.decode(String.self, forKey: .kind); type = try c.decode(String.self, forKey: .type)
        requestID = try c.requiredNullable(UUID.self, forKey: .requestID)
        sessionID = try c.decode(UUID.self, forKey: .sessionID)
        jobID = try c.requiredNullable(UUID.self, forKey: .jobID); sourceID = try c.requiredNullable(UUID.self, forKey: .sourceID)
        timestamp = try c.decode(String.self, forKey: .timestamp); try validateTimestamp(timestamp)
        sequence = try c.decode(Int.self, forKey: .sequence)
        guard sequence > 0 else { throw BackendError.malformedFrame }
        jobRevision = try c.decodeIfPresent(Int.self, forKey: .jobRevision)
        attemptID = try c.decodeIfPresent(UUID.self, forKey: .attemptID)
        // Response to jobs.cancel has a job ID but no attempt/revision in Phase 1.
        if kind == "event", jobID != nil {
            guard let revision = jobRevision, revision >= 0, attemptID != nil else { throw BackendError.malformedFrame }
        }
        if kind == "response" {
            guard let command = CommandType(rawValue: type), requestID != nil else { throw BackendError.malformedFrame }
            payload = .response(try BackendResponse(from: c.superDecoder(forKey: .payload), type: command)); return
        }
        guard kind == "event" else { throw BackendError.malformedFrame }
        switch EventType(identifier: type) {
        case .ready: payload = .ready(try c.decode(Capabilities.self, forKey: .payload))
        case .analysisStarted: payload = .analysisStarted(try c.decode(AnalysisStarted.self, forKey: .payload))
        case .analysisItem: payload = .analysisItem(try c.decode(AnalysisItem.self, forKey: .payload))
        case .analysisCompleted: payload = .analysisCompleted(try c.decode(AnalysisCompleted.self, forKey: .payload))
        case .analysisCancelled: _ = try c.decode(EmptyPayload.self, forKey: .payload); payload = .analysisCancelled
        case .analysisFailed, .downloadFailed, .authFailed, .error: payload = .failure(try c.decode(ErrorPayload.self, forKey: .payload))
        case .downloadStarted: payload = .downloadStarted(try c.decode(DownloadStarted.self, forKey: .payload))
        case .downloadProgress, .downloadProcessing: payload = .progress(try c.decode(Progress.self, forKey: .payload))
        case .downloadCompleted: payload = .downloadCompleted(try c.decode(DownloadCompleted.self, forKey: .payload))
        case .jobCancelled: payload = .jobCancelled(try c.decode(JobCancelled.self, forKey: .payload))
        case .authRequired: payload = .authRequired(try c.decode(AuthenticationRequired.self, forKey: .payload))
        case .diagnostic: payload = .diagnostic(try c.decode(Diagnostic.self, forKey: .payload))
        case .unknown:
            _ = try c.decode(EmptyPayload.self, forKey: .payload) // object required; unknown fields discarded
            payload = .unknown
        }
    }
}
