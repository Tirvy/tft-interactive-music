import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { delimiter, join } from 'node:path'
import { createInterface, type Interface } from 'node:readline'
import type { AppSettings } from '@tft/shared-types/settings'
import { WORKER_PROTOCOL_VERSION, workerMessageSchema } from '@tft/shared-types/protocol'
import { createInitialWorkerStatus, type WorkerStatus } from '@tft/shared-types/worker'
import { errorMessage } from '../errors'
import type { Logger } from '../logger'
import { LineBuffer } from './line-buffer'
import { resolvePythonExecutable } from './python-resolver'

export interface WorkerSupervisorOptions {
  recognitionDir: string | null
  logger: Logger
  getSettings: () => AppSettings
  onStatus?: (status: WorkerStatus) => void
}

const SHUTDOWN_GRACE_MS = 3000
const FORCE_KILL_GRACE_MS = 1000

/**
 * Owns the Python worker child process and its stdio JSON-lines protocol.
 *
 * State transitions:
 *   stopped -> starting -> running -> stopping -> stopped
 *   starting -> error (spawn failure or startup timeout)
 *   running -> disconnected (unexpected exit or heartbeat timeout)
 */
export class WorkerSupervisor {
  private status = createInitialWorkerStatus()
  private child: ChildProcessWithoutNullStreams | null = null
  private stdoutReader: Interface | null = null
  private stderrReader: Interface | null = null
  private readonly lineBuffer = new LineBuffer()
  private startupTimer: NodeJS.Timeout | null = null
  private healthTimer: NodeJS.Timeout | null = null
  private stopRequested = false
  private disposed = false
  private startPromise: Promise<WorkerStatus> | null = null
  private exitPromise: Promise<void> | null = null
  private resolveExit: (() => void) | null = null

  constructor(private readonly options: WorkerSupervisorOptions) {}

  getStatus(): WorkerStatus {
    return {
      ...this.status,
      lastError: this.status.lastError ? { ...this.status.lastError } : null,
    }
  }

  isActive(): boolean {
    return (
      this.child !== null ||
      this.status.state === 'starting' ||
      this.status.state === 'running' ||
      this.status.state === 'stopping'
    )
  }

  async start(): Promise<WorkerStatus> {
    if (this.startPromise) {
      return this.startPromise
    }

    if (this.child) {
      return this.getStatus()
    }

    this.startPromise = Promise.resolve(this.doStart()).finally(() => {
      this.startPromise = null
    })

    return this.startPromise
  }

  async stop(reason = 'user-stopped'): Promise<WorkerStatus> {
    if (this.startPromise) {
      await this.startPromise
    }

    if (!this.child) {
      this.setStatus({
        state: this.status.state === 'error' ? 'error' : 'stopped',
        pid: null,
      })
      return this.getStatus()
    }

    this.stopRequested = true
    this.setStatus({ state: 'stopping' })
    this.send({
      type: 'worker.shutdown',
      schemaVersion: WORKER_PROTOCOL_VERSION,
      reason,
    })

    const exit = this.exitPromise
    if (exit) {
      await Promise.race([exit, delay(SHUTDOWN_GRACE_MS)])
    }

    if (this.child) {
      this.options.logger.warn('worker.shutdown-timeout', { reason })
      this.killChild()
      if (exit) {
        await Promise.race([exit, delay(FORCE_KILL_GRACE_MS)])
      }
    }

    if (this.child) {
      this.forceCleanup()
    }

    this.setStatus({ state: 'stopped', pid: null })
    return this.getStatus()
  }

  async restart(): Promise<WorkerStatus> {
    await this.stop('restart')
    this.setStatus({ restartCount: this.status.restartCount + 1 })
    return this.start()
  }

  dispose(): void {
    this.disposed = true
    this.clearTimers()
    this.closeReaders()

    if (this.child) {
      this.stopRequested = true
      this.killChild()
      this.child = null
    }
  }

  private doStart(): WorkerStatus {
    const settings = this.options.getSettings()

    if (!this.options.recognitionDir) {
      const message =
        'Could not locate apps/recognition. Set the project layout or configure the worker path.'
      this.options.logger.error('worker.recognition-dir-missing')
      this.setStatus({
        state: 'error',
        pid: null,
        lastError: { code: 'recognition_dir_missing', message },
      })
      return this.getStatus()
    }

    const resolved = resolvePythonExecutable(
      this.options.recognitionDir,
      settings.worker.pythonPath,
    )

    this.setStatus({
      state: 'starting',
      pid: null,
      pythonPath: resolved.command,
      workerVersion: null,
      mode: null,
      startedAt: new Date().toISOString(),
      readyAt: null,
      lastHeartbeatAt: null,
      lastPongAt: null,
      lastError: null,
    })

    this.options.logger.info('worker.starting', {
      pythonPath: resolved.command,
      pythonOrigin: resolved.origin,
      recognitionDir: this.options.recognitionDir,
    })

    let child: ChildProcessWithoutNullStreams
    try {
      child = spawn(resolved.command, ['-m', 'tft_recognition.worker'], {
        cwd: this.options.recognitionDir,
        env: {
          ...process.env,
          PYTHONPATH: this.buildPythonPath(this.options.recognitionDir),
          PYTHONUNBUFFERED: '1',
          PYTHONIOENCODING: 'utf-8',
          PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT: 'False',
        },
        stdio: ['pipe', 'pipe', 'pipe'],
        windowsHide: true,
      })
    } catch (error) {
      this.failStart('spawn_failed', errorMessage(error))
      return this.getStatus()
    }

    this.child = child
    this.stopRequested = false
    this.exitPromise = new Promise((resolve) => {
      this.resolveExit = resolve
    })

    child.once('error', (error) => {
      this.options.logger.error('worker.process-error', { message: errorMessage(error) })
      this.failStart('spawn_failed', errorMessage(error))
      this.cleanupChild()
    })

    child.once('exit', (code, signal) => {
      this.handleExit(code, signal)
    })

    this.stdoutReader = createInterface({ input: child.stdout })
    this.stdoutReader.on('line', (line) => {
      this.handleLine(line)
    })
    this.stdoutReader.on('close', () => {
      const remaining = this.lineBuffer.flush()
      for (const line of remaining) {
        this.handleLine(line)
      }
    })

    this.stderrReader = createInterface({ input: child.stderr })
    this.stderrReader.on('line', (line) => {
      if (line.trim().length > 0) {
        this.options.logger.debug('worker.stderr', { line })
      }
    })

    this.startupTimer = setTimeout(() => {
      if (this.status.state !== 'starting') {
        return
      }

      const message = `Worker did not become ready within ${settings.worker.startupTimeoutMs} ms.`
      this.options.logger.error('worker.startup-timeout', {
        timeoutMs: settings.worker.startupTimeoutMs,
      })
      this.setStatus({
        state: 'error',
        lastError: { code: 'startup_timeout', message },
      })
      this.killChild()
      this.cleanupChild()
    }, settings.worker.startupTimeoutMs)

    return this.getStatus()
  }

  private handleLine(line: string): void {
    const parsed = workerMessageSchema.safeParse(safeJsonParse(line))

    if (!parsed.success) {
      this.options.logger.warn('worker.invalid-message', {
        line: line.slice(0, 500),
        issues: parsed.error.issues.map((issue) => issue.message),
      })
      return
    }

    const message = parsed.data

    switch (message.type) {
      case 'worker.ready': {
        this.clearStartupTimer()
        this.options.logger.info('worker.ready', {
          workerVersion: message.workerVersion,
          mode: message.capabilities.mode,
          pid: this.child?.pid,
        })
        this.setStatus({
          state: 'running',
          pid: this.child?.pid ?? null,
          workerVersion: message.workerVersion,
          mode: message.capabilities.mode,
          readyAt: message.startedAt,
          lastHeartbeatAt: new Date().toISOString(),
          lastError: null,
        })
        this.startHealthTimer()
        break
      }

      case 'worker.heartbeat': {
        this.setStatus({ lastHeartbeatAt: new Date().toISOString() })
        break
      }

      case 'worker.pong': {
        this.setStatus({
          lastPongAt: new Date().toISOString(),
          lastHeartbeatAt: new Date().toISOString(),
        })
        break
      }

      case 'worker.stopping': {
        this.options.logger.info('worker.stopping', { reason: message.reason })
        break
      }

      case 'worker.error': {
        this.options.logger.error('worker.reported-error', {
          code: message.code,
          message: message.message,
          detail: message.detail,
        })
        this.setStatus({
          lastError: {
            code: message.code,
            message: message.message,
            ...(message.detail ? { detail: message.detail } : {}),
          },
        })
        break
      }
    }
  }

  private handleExit(code: number | null, signal: NodeJS.Signals | null): void {
    const wasStopping = this.stopRequested
    const previousState = this.status.state

    this.clearTimers()
    this.closeReaders()
    this.child = null
    this.resolveExit?.()
    this.resolveExit = null
    this.exitPromise = null
    this.stopRequested = false

    if (this.disposed) {
      return
    }

    if (previousState === 'error') {
      this.setStatus({ state: 'error', pid: null })
      return
    }

    if (wasStopping || previousState === 'stopping') {
      this.options.logger.info('worker.stopped', { code, signal })
      this.setStatus({
        state: 'stopped',
        pid: null,
        readyAt: null,
        lastHeartbeatAt: null,
        lastPongAt: null,
      })
      return
    }

    const message = `Worker exited unexpectedly (code ${code ?? 'none'}, signal ${signal ?? 'none'}).`
    this.options.logger.warn('worker.exited', { code, signal })
    this.setStatus({
      state: 'disconnected',
      pid: null,
      lastError: { code: 'worker_exited', message },
    })
  }

  private startHealthTimer(): void {
    this.clearHealthTimer()
    const settings = this.options.getSettings()

    this.healthTimer = setInterval(() => {
      if (this.status.state !== 'running' || !this.child) {
        return
      }

      const reference = this.status.lastHeartbeatAt ?? this.status.readyAt
      const referenceTime = reference ? Date.parse(reference) : Number.NaN
      const age = Number.isFinite(referenceTime) ? Date.now() - referenceTime : 0

      if (age > settings.worker.heartbeatTimeoutMs) {
        const message = `No worker heartbeat for ${age} ms (timeout ${settings.worker.heartbeatTimeoutMs} ms).`
        this.options.logger.error('worker.heartbeat-timeout', {
          ageMs: age,
          timeoutMs: settings.worker.heartbeatTimeoutMs,
        })
        this.setStatus({
          state: 'disconnected',
          lastError: { code: 'heartbeat_timeout', message },
        })
        this.killChild()
        return
      }

      this.send({
        type: 'worker.ping',
        schemaVersion: WORKER_PROTOCOL_VERSION,
        requestId: randomUUID(),
        sentAt: new Date().toISOString(),
      })
    }, settings.worker.heartbeatIntervalMs)
  }

  private send(message: {
    type: 'worker.ping' | 'worker.shutdown'
    schemaVersion: number
    [key: string]: unknown
  }): void {
    if (!this.child || this.child.stdin.destroyed) {
      return
    }

    try {
      this.child.stdin.write(`${JSON.stringify(message)}\n`)
    } catch (error) {
      this.options.logger.warn('worker.write-failed', { message: errorMessage(error) })
    }
  }

  private failStart(code: string, message: string): void {
    this.clearTimers()
    this.setStatus({
      state: 'error',
      pid: null,
      lastError: { code, message },
    })
  }

  private setStatus(patch: Partial<WorkerStatus>): void {
    this.status = {
      ...this.status,
      ...patch,
      updatedAt: new Date().toISOString(),
    }

    if (!this.disposed) {
      this.options.onStatus?.(this.getStatus())
    }
  }

  private cleanupChild(): void {
    this.clearTimers()
    this.closeReaders()
    this.child = null
    this.resolveExit?.()
    this.resolveExit = null
    this.exitPromise = null
  }

  private forceCleanup(): void {
    this.killChild()
    this.cleanupChild()
    this.setStatus({ state: 'stopped', pid: null })
  }

  private killChild(): void {
    if (!this.child) {
      return
    }

    try {
      this.child.kill()
    } catch (error) {
      this.options.logger.warn('worker.kill-failed', { message: errorMessage(error) })
    }
  }

  private clearStartupTimer(): void {
    if (this.startupTimer) {
      clearTimeout(this.startupTimer)
      this.startupTimer = null
    }
  }

  private clearHealthTimer(): void {
    if (this.healthTimer) {
      clearInterval(this.healthTimer)
      this.healthTimer = null
    }
  }

  private clearTimers(): void {
    this.clearStartupTimer()
    this.clearHealthTimer()
  }

  private closeReaders(): void {
    for (const reader of [this.stdoutReader, this.stderrReader]) {
      if (reader) {
        try {
          reader.close()
        } catch {
          // Already closed.
        }
      }
    }
    this.stdoutReader = null
    this.stderrReader = null
  }

  private buildPythonPath(recognitionDir: string): string {
    const sourcePath = join(recognitionDir, 'src')
    const existing = process.env['PYTHONPATH']
    return existing ? `${sourcePath}${delimiter}${existing}` : sourcePath
  }
}

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value)
  } catch {
    return undefined
  }
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds)
  })
}
