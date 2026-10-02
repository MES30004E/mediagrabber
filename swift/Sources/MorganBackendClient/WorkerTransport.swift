import Foundation
import Dispatch
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

public struct WorkerConfiguration: Sendable {
    public let executable: URL
    public let arguments: [String]
    public let workingDirectory: URL?
    public let environment: [String: String]?
    public let requestTimeout: TimeInterval
    public let shutdownTimeout: TimeInterval
    public init(executable: URL, arguments: [String] = ["-m", "morgan_media_downloader.backend"],
                workingDirectory: URL? = nil, environment: [String: String]? = nil,
                requestTimeout: TimeInterval = 10, shutdownTimeout: TimeInterval = 10) {
        self.executable = executable; self.arguments = arguments; self.workingDirectory = workingDirectory
        self.environment = environment; self.requestTimeout = requestTimeout; self.shutdownTimeout = shutdownTimeout
    }
}

/// One write ticket per pending request. Cancellation is checked before each
/// nonblocking chunk; a partially written frame cannot be repaired or replayed.
final class WriteTicket: @unchecked Sendable {
    private let lock = NSLock()
    private var stopped = false
    func cancel() { lock.lock(); stopped = true; lock.unlock() }
    var cancelled: Bool { lock.lock(); defer { lock.unlock() }; return stopped }
}

/// File descriptors are owned here. Blocking reads use dedicated Dispatch queues,
/// not Swift's cooperative executor. stdout deliveries rendezvous with the actor
/// so queued incoming chunks cannot grow without bound. stderr is always drained
/// independently and discarded; it is never decoded, retained or logged.
final class WorkerTransport: @unchecked Sendable {
    private let process = Process()
    private let input = Pipe()
    private let output = Pipe()
    private let diagnostics = Pipe()
    private let writer = DispatchQueue(label: "morgan.worker.stdin")
    private let stdoutReader = DispatchQueue(label: "morgan.worker.stdout")
    private let stderrReader = DispatchQueue(label: "morgan.worker.stderr")
    private let lock = NSLock()
    private var closed = false
    private var inputClosed = false
    private let writeTimeout: TimeInterval
    private let receive: @Sendable (Data?, BackendError?, @escaping @Sendable () -> Void) -> Void
    private let exited: @Sendable (Int32) -> Void

    init(configuration: WorkerConfiguration,
         receive: @escaping @Sendable (Data?, BackendError?, @escaping @Sendable () -> Void) -> Void,
         exited: @escaping @Sendable (Int32) -> Void) {
        writeTimeout = configuration.requestTimeout
        self.receive = receive; self.exited = exited
        process.executableURL = configuration.executable; process.arguments = configuration.arguments
        process.currentDirectoryURL = configuration.workingDirectory; process.environment = configuration.environment
        process.standardInput = input; process.standardOutput = output; process.standardError = diagnostics
    }
    func launch() throws {
        let fd = input.fileHandleForWriting.fileDescriptor
        // Per-descriptor Darwin option: never change the host application's global SIGPIPE disposition.
        #if canImport(Darwin)
        guard fcntl(fd, F_SETNOSIGPIPE, 1) != -1 else { throw BackendError.transportFailure }
        #endif
        guard fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK) != -1 else { throw BackendError.transportFailure }
        process.terminationHandler = { [weak self] process in self?.exited(process.terminationStatus) }
        do { try process.run() } catch { throw BackendError.transportFailure }
        // Parent must not retain duplicate child ends: otherwise EOF is concealed.
        input.fileHandleForReading.closeFile()
        output.fileHandleForWriting.closeFile()
        diagnostics.fileHandleForWriting.closeFile()
        stdoutReader.async { [self] in
            while true {
                do {
                    let bytes = try output.fileHandleForReading.read(upToCount: 65536) ?? Data()
                    let done = DispatchSemaphore(value: 0)
                    receive(bytes.isEmpty ? nil : bytes, nil) { done.signal() }
                    done.wait()
                    if bytes.isEmpty { break }
                } catch {
                    receive(nil, .transportFailure, {})
                    break
                }
            }
            output.fileHandleForReading.closeFile()
        }
        stderrReader.async { [self] in
            while let bytes = try? diagnostics.fileHandleForReading.read(upToCount: 65536), !bytes.isEmpty {}
            diagnostics.fileHandleForReading.closeFile()
        }
    }
    var statusIfExited: Int32? { process.isRunning ? nil : process.terminationStatus }
    func write(_ bytes: Data, ticket: WriteTicket, completion: @escaping @Sendable (BackendError?) -> Void) {
        writer.async { [self] in
            lock.lock(); let unavailable = closed || inputClosed; lock.unlock()
            guard !unavailable else { completion(.transportFailure); return }
            let deadline = Date().addingTimeInterval(writeTimeout)
            var offset = 0
            let fd = input.fileHandleForWriting.fileDescriptor
            while offset < bytes.count {
                if ticket.cancelled {
                    completion(offset == 0 ? .cancelled : .transportFailure); return
                }
                if Date() >= deadline { completion(.transportFailure); return }
                let count: Int = bytes.withUnsafeBytes { raw in
                    #if canImport(Darwin)
                    return Darwin.write(fd, raw.baseAddress!.advanced(by: offset), bytes.count - offset)
                    #else
                    return Glibc.write(fd, raw.baseAddress!.advanced(by: offset), bytes.count - offset)
                    #endif
                }
                if count > 0 { offset += count; continue }
                if count < 0 && errno == EINTR { continue }
                guard count < 0 && (errno == EAGAIN || errno == EWOULDBLOCK) else {
                    completion(errno == EPIPE ? .workerEOF : .transportFailure); return
                }
                var descriptor = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
                _ = poll(&descriptor, 1, 50) // dedicated writer queue only, cancellation checked every 50ms
            }
            completion(nil)
        }
    }
    func closeInput() {
        writer.async { [self] in
            lock.lock(); let shouldClose = !inputClosed; inputClosed = true; lock.unlock()
            if shouldClose { input.fileHandleForWriting.closeFile() }
        }
    }
    func terminate() {
        lock.lock(); let first = !closed; closed = true; lock.unlock()
        if first {
            if process.isRunning { process.terminate() }
            closeInput()
            // Bound ownership even if a worker ignores SIGTERM; only this Process
            // instance is signalled, and no stale PID is persisted or reused.
            DispatchQueue.global().asyncAfter(deadline: .now() + 1) { [self] in
                if process.isRunning { _ = kill(process.processIdentifier, SIGKILL) }
            }
        }
    }
}
