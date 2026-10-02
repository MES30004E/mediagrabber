import Foundation

public enum WorkerLifecycle: Sendable, Equatable {
    case idle, starting, ready, stopping, stopped
    case failed(BackendError)
}

/// One client owns one worker, one session and one bounded, single-consumer event
/// stream. No request is replayed after failure. Call shutdown or abort explicitly.
public actor BackendClient {
    public nonisolated let events: AsyncThrowingStream<BackendMessage, Error>
    private let eventContinuation: AsyncThrowingStream<BackendMessage, Error>.Continuation
    private var state: WorkerLifecycle = .idle
    private var transport: WorkerTransport?
    private var configuration: WorkerConfiguration?
    private var sessionID: UUID?
    private var sequence = 0
    private var framer = JSONLineFramer()
    private var stdoutEOF = false
    private var exitStatus: Int32?
    private var shutdownAcknowledged = false
    private var exitWaiter: CheckedContinuation<Void, Error>?
    private var exitTimer: Task<Void, Never>?
    private var eofTimer: Task<Void, Never>?
    private struct Registration {
        let type: CommandType
        let jobID: UUID?
        var jobs = Set<UUID>()
    }
    private struct Pending {
        let continuation: CheckedContinuation<BackendMessage, Error>
        let ticket: WriteTicket
        let timer: Task<Void, Never>
    }
    private var requests: [UUID: Registration] = [:]
    private var pending: [UUID: Pending] = [:]

    public init() {
        var continuation: AsyncThrowingStream<BackendMessage, Error>.Continuation!
        events = AsyncThrowingStream(bufferingPolicy: .bufferingOldest(512)) { continuation = $0 }
        eventContinuation = continuation
    }
    deinit { transport?.terminate() }
    public func lifecycle() -> WorkerLifecycle { state }

    public func start(_ configuration: WorkerConfiguration) async throws -> Capabilities {
        guard state == .idle, configuration.requestTimeout.isFinite, configuration.requestTimeout > 0,
              configuration.requestTimeout <= 300, configuration.shutdownTimeout.isFinite,
              configuration.shutdownTimeout > 0, configuration.shutdownTimeout <= 300 else { throw BackendError.invalidLifecycle }
        self.configuration = configuration; state = .starting
        let worker = WorkerTransport(configuration: configuration, receive: { [weak self] bytes, error, done in
            Task { await self?.receive(bytes, error: error); done() }
        }, exited: { [weak self] status in Task { await self?.didExit(status) } })
        transport = worker
        do {
            try worker.launch()
            let hello = try await issue(BackendCommand(.hello(HelloPayload())))
            guard case .response(let response) = hello.payload, case .some(.capabilities(let capabilities)) = response.result else {
                throw BackendError.malformedFrame
            }
            try validateVersion(capabilities.selectedVersion)
            guard capabilities.maxFrameBytes == ProtocolContract.maximumFrameBytes,
                  [CommandType.hello, .ping, .shutdown, .analyse, .cancelAnalysis].allSatisfy({ capabilities.capabilities.contains($0.rawValue) }) else {
                throw BackendError.incompatibleProtocolVersion
            }
            if case .failed(let error) = state { throw error }
            guard state == .starting else { throw BackendError.invalidLifecycle }
            sessionID = hello.sessionID
            state = .ready
            return capabilities
        } catch {
            let safe = (error as? BackendError) ?? .transportFailure
            fail(safe); throw safe
        }
    }
    public func send(_ payload: CommandPayload, jobID: UUID? = nil) async throws -> BackendMessage {
        guard state == .ready, payload.type != .hello, payload.type != .shutdown else { throw BackendError.invalidLifecycle }
        if payload.type == .cancelJob && jobID == nil { throw BackendError.malformedFrame }
        return try await issue(BackendCommand(payload, sessionID: sessionID, jobID: jobID))
    }
    private func issue(_ command: BackendCommand) async throws -> BackendMessage {
        guard pending.count < 128, requests.count < 65536 else { throw BackendError.capacityExceeded }
        let bytes = try command.framed()
        let id = command.requestID
        let ticket = WriteTicket()
        let timeout = configuration?.requestTimeout ?? 10
        return try await withTaskCancellationHandler(operation: {
            if Task.isCancelled { throw BackendError.cancelled }
            return try await withCheckedThrowingContinuation { continuation in
                requests[id] = Registration(type: command.type, jobID: command.jobID)
                let timer = Task { [weak self] in
                    do { try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000)) }
                    catch { return }
                    await self?.expire(id, error: .timeout)
                }
                pending[id] = Pending(continuation: continuation, ticket: ticket, timer: timer)
                transport?.write(bytes, ticket: ticket) { [weak self] error in
                    if let error { Task { await self?.writeFailed(id, error: error) } }
                }
            }
        }, onCancel: { [weak self] in
            ticket.cancel()
            Task { await self?.expire(id, error: .cancelled) }
        })
    }
    private func expire(_ id: UUID, error: BackendError) {
        guard let waiter = pending.removeValue(forKey: id) else { return }
        waiter.timer.cancel(); waiter.ticket.cancel()
        waiter.continuation.resume(throwing: error)
    }
    private func writeFailed(_ id: UUID, error: BackendError) {
        if error == .cancelled { expire(id, error: error) }
        else if error == .workerEOF {
            // EPIPE may race the reader and Process termination callback. Let
            // buffered stdout and the exit status determine EOF versus crash.
            scheduleEOFCheck()
        } else { fail(error) } // partial frame or closed pipe: stream cannot be safely repaired
    }
    private func receive(_ bytes: Data?, error: BackendError?) {
        if case .failed = state { return }
        if state == .stopped { return }
        if let error { fail(error); return }
        guard let bytes else {
            if let error = framer.finish() { fail(error); return }
            stdoutEOF = true; finishExitIfReady(); scheduleEOFCheck(); return
        }
        for frame in framer.append(bytes) {
            do {
                switch frame {
                case .failure(let error): throw error
                case .frame(let data): try accept(BackendMessage.decode(data))
                }
            } catch { fail((error as? BackendError) ?? .malformedFrame); return }
        }
    }
    private func accept(_ message: BackendMessage) throws {
        guard message.sequence == sequence + 1 else { throw BackendError.correlationFailure }
        sequence = message.sequence
        if let sessionID {
            guard sessionID == message.sessionID else { throw BackendError.correlationFailure }
        } else {
            guard let id = message.requestID, requests[id]?.type == .hello else { throw BackendError.correlationFailure }
            sessionID = message.sessionID
        }
        if message.kind == "response" {
            guard let id = message.requestID, var registration = requests[id], registration.type.rawValue == message.type,
                  registration.jobID == message.jobID, case .response(let response) = message.payload else {
                throw BackendError.correlationFailure
            }
            if response.status != .rejected {
                let expected: ResponseStatus = [.hello, .ping, .shutdown].contains(registration.type) ? .completed : .accepted
                guard response.status == expected else { throw BackendError.malformedFrame }
            }
            if case .some(.jobs(let result)) = response.result {
                registration.jobs = Set(result.jobs.map(\.jobID)); requests[id] = registration
            }
            if registration.type == .shutdown, response.status == .completed { shutdownAcknowledged = true }
            if let waiter = pending.removeValue(forKey: id) {
                waiter.timer.cancel()
                if let error = response.error { waiter.continuation.resume(throwing: error.mapped) }
                else { waiter.continuation.resume(returning: message) }
            } // matching late response after timeout/cancellation is discarded, never replayed
            return
        }
        guard let event = message.eventType else { throw BackendError.malformedFrame }
        if let id = message.requestID {
            guard let registration = requests[id] else { throw BackendError.correlationFailure }
            switch event {
            case .ready: guard registration.type == .hello else { throw BackendError.correlationFailure }
            case .analysisStarted, .analysisItem, .analysisCompleted, .analysisFailed, .analysisCancelled:
                guard registration.type == .analyse, message.jobID == nil else { throw BackendError.correlationFailure }
            case .downloadStarted, .downloadProgress, .downloadProcessing, .downloadCompleted, .downloadFailed, .jobCancelled:
                guard registration.type == .enqueue, let job = message.jobID, registration.jobs.contains(job) else { throw BackendError.correlationFailure }
            default: break
            }
            if case .analysisItem(let p) = message.payload, p.item.sourceID != message.sourceID { throw BackendError.correlationFailure }
            if event == .error, let error = message.operationError { expire(id, error: error) }
        } else {
            switch event {
            case .error, .diagnostic, .unknown: break
            default: throw BackendError.correlationFailure
            }
        }
        switch eventContinuation.yield(message) {
        case .dropped: throw BackendError.consumerTooSlow
        case .terminated: throw BackendError.cancelled
        case .enqueued: break
        @unknown default: throw BackendError.consumerTooSlow
        }
    }
    private func scheduleEOFCheck() {
        guard eofTimer == nil else { return }
        eofTimer = Task { [weak self] in
            do { try await Task.sleep(nanoseconds: 250_000_000) } catch { return }
            await self?.outputUnavailable()
        }
    }
    private func outputUnavailable() {
        eofTimer = nil
        if state == .stopped { return }
        if case .failed = state { return }
        if let status = transport?.statusIfExited { exitStatus = status }
        finishExitIfReady()
        if state == .stopped { return }
        if case .failed = state { return }
        // An acknowledged shutdown owns a separate bounded exit timeout.
        if state == .stopping && shutdownAcknowledged { return }
        fail(.workerEOF)
    }
    private func didExit(_ status: Int32) { exitStatus = status; finishExitIfReady() }
    private func finishExitIfReady() {
        guard stdoutEOF, let status = exitStatus else { return }
        if case .failed = state { return }
        if state == .stopping, shutdownAcknowledged, status == 0 {
            for id in Array(pending.keys) { expire(id, error: .workerEOF) }
            state = .stopped; transport?.closeInput(); transport = nil
            eofTimer?.cancel(); eofTimer = nil
            eventContinuation.finish(); exitTimer?.cancel(); exitTimer = nil
            exitWaiter?.resume(); exitWaiter = nil
        } else { fail(status == 0 ? .workerEOF : .workerCrash(status)) }
    }
    public func shutdown() async throws {
        if state == .stopped { return }
        guard state == .ready else { throw BackendError.invalidLifecycle }
        state = .stopping
        do {
            _ = try await issue(BackendCommand(.shutdown, sessionID: sessionID))
            transport?.closeInput()
            if state == .stopped { return }
            if case .failed(let error) = state { throw error }
            let timeout = configuration?.shutdownTimeout ?? 10
            try await withTaskCancellationHandler(operation: {
                if Task.isCancelled { throw BackendError.cancelled }
                try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                    exitWaiter = continuation
                    exitTimer = Task { [weak self] in
                        do { try await Task.sleep(nanoseconds: UInt64(timeout * 1_000_000_000)) } catch { return }
                        await self?.fail(.timeout)
                    }
                    finishExitIfReady()
                }
            }, onCancel: { [weak self] in Task { await self?.abort() } })
        } catch {
            let safe = (error as? BackendError) ?? .cancelled
            fail(safe); throw safe
        }
    }
    /// Explicit fallback after failure or a cancelled owner. Does not claim graceful operation cancellation.
    public func abort() { fail(.cancelled) }
    private func fail(_ error: BackendError) {
        if case .failed = state { return }
        if state == .stopped { return }
        state = .failed(error)
        for id in Array(pending.keys) { expire(id, error: error) }
        exitTimer?.cancel(); exitTimer = nil
        eofTimer?.cancel(); eofTimer = nil
        exitWaiter?.resume(throwing: error); exitWaiter = nil
        transport?.terminate()
        eventContinuation.finish(throwing: error)
    }
}
