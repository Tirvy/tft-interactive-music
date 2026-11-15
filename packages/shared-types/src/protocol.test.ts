import { describe, expect, it } from 'vitest'
import {
  WORKER_PROTOCOL_VERSION,
  parseWorkerMessage,
  workerMessageSchema,
  workerPingMessageSchema,
} from './protocol'

describe('worker protocol', () => {
  it('parses a ready message', () => {
    const parsed = parseWorkerMessage(
      JSON.stringify({
        type: 'worker.ready',
        schemaVersion: 1,
        workerVersion: '0.1.0',
        startedAt: '2026-11-15T10:00:00.000Z',
        capabilities: {
          mode: 'stub',
          ocrEngine: null,
          recognition: false,
          liveCapture: false,
        },
      }),
    )

    expect(parsed.type).toBe('worker.ready')
    if (parsed.type === 'worker.ready') {
      expect(parsed.capabilities.mode).toBe('stub')
    }
  })

  it('rejects an incompatible schema version', () => {
    const result = workerMessageSchema.safeParse({
      type: 'worker.heartbeat',
      schemaVersion: WORKER_PROTOCOL_VERSION + 1,
      sequence: 1,
      sentAt: '2026-11-15T10:00:00.000Z',
      uptimeMs: 10,
    })

    expect(result.success).toBe(false)
  })

  it('rejects unknown message types', () => {
    expect(
      workerMessageSchema.safeParse({
        type: 'worker.unknown',
        schemaVersion: 1,
      }).success,
    ).toBe(false)
  })

  it('builds a valid desktop ping', () => {
    expect(
      workerPingMessageSchema.parse({
        type: 'worker.ping',
        schemaVersion: 1,
        requestId: 'req-1',
        sentAt: '2026-11-15T10:00:00.000Z',
      }).requestId,
    ).toBe('req-1')
  })
})
