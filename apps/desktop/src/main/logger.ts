import {
  appendFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  renameSync,
  statSync,
  unlinkSync,
} from 'node:fs'
import { join } from 'node:path'

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export type LogContext = Record<string, unknown>

interface LoggerOptions {
  maxBytes?: number
  mirrorToConsole?: boolean
}

const DEFAULT_MAX_BYTES = 5 * 1024 * 1024

/**
 * Small append-only NDJSON logger. Diagnostic logs stay local in userData
 * and rotate once they exceed the configured size.
 */
export class Logger {
  readonly filePath: string

  private readonly maxBytes: number
  private readonly mirrorToConsole: boolean

  constructor(logDir: string, options: LoggerOptions = {}) {
    mkdirSync(logDir, { recursive: true })
    this.filePath = join(logDir, 'main.log')
    this.maxBytes = options.maxBytes ?? DEFAULT_MAX_BYTES
    this.mirrorToConsole = options.mirrorToConsole ?? false

    if (!existsSync(this.filePath)) {
      appendFileSync(this.filePath, '', 'utf8')
    }
  }

  debug(message: string, context?: LogContext): void {
    this.write('debug', message, context)
  }

  info(message: string, context?: LogContext): void {
    this.write('info', message, context)
  }

  warn(message: string, context?: LogContext): void {
    this.write('warn', message, context)
  }

  error(message: string, context?: LogContext): void {
    this.write('error', message, context)
  }

  tail(maxLines = 200): string[] {
    if (!existsSync(this.filePath)) {
      return []
    }

    const content = readFileSync(this.filePath, 'utf8')
    return content
      .split(/\r?\n/)
      .filter((line) => line.length > 0)
      .slice(-maxLines)
  }

  private write(level: LogLevel, message: string, context?: LogContext): void {
    const entry = {
      timestamp: new Date().toISOString(),
      level,
      message,
      ...(context ? { context } : {}),
    }

    try {
      this.rotateIfNeeded()
      appendFileSync(this.filePath, `${JSON.stringify(entry)}\n`, 'utf8')
    } catch (error) {
      if (this.mirrorToConsole) {
        console.error('Failed to write log entry', error)
      }
    }

    if (this.mirrorToConsole) {
      const write =
        level === 'error' ? console.error : level === 'warn' ? console.warn : console.log
      write(`[${level}] ${message}`, context ?? '')
    }
  }

  private rotateIfNeeded(): void {
    if (!existsSync(this.filePath)) {
      return
    }

    if (statSync(this.filePath).size < this.maxBytes) {
      return
    }

    const rotatedPath = `${this.filePath}.1`
    if (existsSync(rotatedPath)) {
      unlinkSync(rotatedPath)
    }
    renameSync(this.filePath, rotatedPath)
    appendFileSync(this.filePath, '', 'utf8')
  }
}
