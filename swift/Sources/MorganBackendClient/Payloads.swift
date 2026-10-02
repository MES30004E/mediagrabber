import Foundation

public struct HelloPayload: Codable, Sendable {
    public let supportedVersions: [String]
    enum CodingKeys: String, CodingKey { case supportedVersions = "supported_versions" }
    public init(supportedVersions: [String] = [ProtocolContract.version]) { self.supportedVersions = supportedVersions }
}
public struct ProxyConfiguration: Codable, Sendable {
    public let mode: String
    public let host: String
    public let port: Int
    public init(mode: String = "Direct", host: String = "", port: Int = 0) {
        self.mode = mode; self.host = host; self.port = port
    }
}
/// References to user-selected files, never file contents or credential values.
public struct AnalysisConfiguration: Codable, Sendable {
    public var authenticationMode: String?
    public var cookiesBrowser: String?
    public var browserProfile: String?
    public var cookiesFile: String?
    public var providerURL: String?
    public var providerHome: String?
    public var proxy: ProxyConfiguration?
    enum CodingKeys: String, CodingKey {
        case authenticationMode = "authentication_mode", cookiesBrowser = "cookies_browser"
        case browserProfile = "browser_profile", cookiesFile = "cookies_file"
        case providerURL = "provider_url", providerHome = "provider_home", proxy
    }
    public init() {}
}
public struct AnalysePayload: Codable, Sendable {
    public let inputs: [String]
    public let purpose: String?
    public let settingsRevision: Int?
    public let config: AnalysisConfiguration?
    enum CodingKeys: String, CodingKey { case inputs, purpose, config; case settingsRevision = "settings_revision" }
    public init(inputs: [String], config: AnalysisConfiguration? = nil) {
        self.inputs = inputs; self.config = config; self.purpose = "preview"; self.settingsRevision = nil
    }
}
public struct DownloadOptions: Codable, Sendable {
    public var downloadDir: String
    public var compatibility: String?
    public var quality: String?
    public var container: String?
    public var audioFormat: String?
    public var audioBitrate: String?
    public var subtitleSource: String?
    public var subtitleLanguage: String?
    public var filenameTemplate: String?
    public var embedThumbnail: Bool?
    public var embedMetadata: Bool?
    public var embedChapters: Bool?
    public var embedSubtitles: Bool?
    public var writeSubtitles: Bool?
    public var verifyPostprocessing: Bool?
    public var keepOriginal: Bool?
    enum CodingKeys: String, CodingKey {
        case compatibility, quality, container
        case downloadDir = "download_dir", audioFormat = "audio_format", audioBitrate = "audio_bitrate"
        case subtitleSource = "subtitle_source", subtitleLanguage = "subtitle_language", filenameTemplate = "filename_template"
        case embedThumbnail = "embed_thumbnail", embedMetadata = "embed_metadata", embedChapters = "embed_chapters"
        case embedSubtitles = "embed_subtitles", writeSubtitles = "write_subtitles"
        case verifyPostprocessing = "verify_postprocessing", keepOriginal = "keep_original"
    }
    public init(downloadDir: String) { self.downloadDir = downloadDir }
}
public struct EnqueuePayload: Codable, Sendable {
    public let analysisRequestID: UUID
    public let sourceIDs: [UUID]
    public let options: DownloadOptions
    public let config: AnalysisConfiguration?
    enum CodingKeys: String, CodingKey {
        case analysisRequestID = "analysis_request_id", sourceIDs = "source_ids", options, config
    }
    public init(analysisRequestID: UUID, sourceIDs: [UUID], options: DownloadOptions, config: AnalysisConfiguration? = nil) {
        self.analysisRequestID = analysisRequestID; self.sourceIDs = sourceIDs; self.options = options; self.config = config
    }
}
public struct CancelAnalysisPayload: Codable, Sendable {
    public let targetRequestID: UUID
    enum CodingKeys: String, CodingKey { case targetRequestID = "target_request_id" }
    public init(targetRequestID: UUID) { self.targetRequestID = targetRequestID }
}
public struct CancelJobPayload: Codable, Sendable {
    public let expectedJobRevision: Int
    enum CodingKeys: String, CodingKey { case expectedJobRevision = "expected_job_revision" }
    public init(expectedJobRevision: Int) { self.expectedJobRevision = expectedJobRevision }
}
public struct Capabilities: Codable, Sendable {
    public let selectedVersion: String
    public let capabilities: [String]
    public let maxFrameBytes: Int
    public let maxAnalysisInputs: Int
    public let maxConcurrentOperations: Int
    public let maxSessionItems: Int
    public let durableJobs: Bool
    public let runtimeSource: String
    public let secretIPC: Bool
    enum CodingKeys: String, CodingKey {
        case selectedVersion = "selected_version", capabilities, maxFrameBytes = "max_frame_bytes"
        case maxAnalysisInputs = "max_analysis_inputs", maxConcurrentOperations = "max_concurrent_operations"
        case maxSessionItems = "max_session_items", durableJobs = "durable_jobs", runtimeSource = "runtime_source", secretIPC = "secret_ipc"
    }
}
public struct SafeBackendError: Codable, Sendable {
    public let code: String
    public let category: String
    public let stage: String
    public let safeMessage: String
    public let retryable: Bool
    public let retryOptions: [String]
    public let diagnosticID: UUID?
    enum CodingKeys: String, CodingKey {
        case code, category, stage, safeMessage = "safe_message", retryable
        case retryOptions = "retry_options", diagnosticID = "diagnostic_id"
    }
    var mapped: BackendError {
        // Only codes matching the static identifier grammar reach errors; descriptions never print codes.
        let safeCode = code.range(of: "^[a-z][a-z0-9_.]{0,95}$", options: .regularExpression) != nil ? code : "backend.failed"
        if code == "protocol.unsupported_version" { return .incompatibleProtocolVersion }
        if category == "auth" { return .authenticationRequired }
        return category == "protocol" ? .protocolError(safeCode) : .operationFailed(safeCode)
    }
}
public struct MediaItem: Codable, Sendable {
    public let sourceID: UUID
    public let title: String
    public let uploader: String
    public let displayURL: String
    public let originalDisplayURL: String
    public let durationSeconds: Double?
    public let source: String
    public let playlistIndex: Double?
    public let confidence: Double?
    public let collectionTitle: String
    public let collectionType: String
    public let availableSubtitles: [String]
    public let automaticCaptions: [String]
    enum CodingKeys: String, CodingKey {
        case sourceID = "source_id", title, uploader, displayURL = "display_url", originalDisplayURL = "original_display_url"
        case durationSeconds = "duration_seconds", source, playlistIndex = "playlist_index", confidence
        case collectionTitle = "collection_title", collectionType = "collection_type"
        case availableSubtitles = "available_subtitles", automaticCaptions = "automatic_captions"
    }
}
public struct Progress: Codable, Sendable {
    public let stage: String
    public let downloadedBytes: Double
    public let totalBytes: Double?
    public let totalIsEstimate: Bool
    public let percent: Double?
    public let speedBytesPerSecond: Double
    public let etaSeconds: Double?
    public let fragmentIndex: Double?
    public let fragmentCount: Double?
    enum CodingKeys: String, CodingKey {
        case stage, downloadedBytes = "downloaded_bytes", totalBytes = "total_bytes", totalIsEstimate = "total_is_estimate"
        case percent, speedBytesPerSecond = "speed_bytes_per_second", etaSeconds = "eta_seconds"
        case fragmentIndex = "fragment_index", fragmentCount = "fragment_count"
    }
}
public struct AnalysisStarted: Codable, Sendable { public let operationID: UUID; enum CodingKeys: String, CodingKey { case operationID = "operation_id" } }
public struct AnalysisItem: Codable, Sendable { public let item: MediaItem }
public struct AnalysisCompleted: Codable, Sendable {
    public let count: Int
    public let effectiveAuthentication: String
    enum CodingKeys: String, CodingKey { case count, effectiveAuthentication = "effective_authentication" }
}
public struct ErrorPayload: Codable, Sendable { public let error: SafeBackendError }
public struct AuthenticationRequired: Codable, Sendable { public let mode: String }
public struct DownloadStarted: Codable, Sendable {
    public let runtimeVersion: String
    public let formatsPlayable: Int
    enum CodingKeys: String, CodingKey { case runtimeVersion = "runtime_version", formatsPlayable = "formats_playable" }
}
public struct DownloadCompleted: Codable, Sendable {
    public let status: String
    public let finalFiles: [String]
    public let warnings: [String]
    public let verificationPerformed: Bool
    enum CodingKeys: String, CodingKey { case status, finalFiles = "final_files", warnings, verificationPerformed = "verification_performed" }
}
public struct JobCancelled: Codable, Sendable { public let retainedFiles: Bool?; public let error: SafeBackendError?; enum CodingKeys: String, CodingKey { case retainedFiles = "retained_files", error } }
public struct Diagnostic: Codable, Sendable { public let category: String; public let level: String; public let safeMessage: String; enum CodingKeys: String, CodingKey { case category, level, safeMessage = "safe_message" } }
public struct JobIdentity: Codable, Sendable {
    public let jobID: UUID; public let sourceID: UUID; public let attemptID: UUID; public let jobRevision: Int
    enum CodingKeys: String, CodingKey { case jobID = "job_id", sourceID = "source_id", attemptID = "attempt_id", jobRevision = "job_revision" }
}
public struct OperationAccepted: Codable, Sendable { public let operationID: UUID; enum CodingKeys: String, CodingKey { case operationID = "operation_id" } }
public struct JobsAccepted: Codable, Sendable { public let jobs: [JobIdentity] }
public struct CancellationAccepted: Codable, Sendable { public let cancellation: String }
public struct EmptyPayload: Codable, Sendable {
    public init() {}
    public init(from decoder: Decoder) throws { _ = try decoder.container(keyedBy: AnyKey.self) }
    public func encode(to encoder: Encoder) throws { _ = encoder.container(keyedBy: AnyKey.self) }
    private struct AnyKey: CodingKey {
        let stringValue: String
        let intValue: Int? = nil
        init?(stringValue: String) { self.stringValue = stringValue }
        init?(intValue: Int) { return nil }
    }
}
