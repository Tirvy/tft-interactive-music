import { describe, expect, it } from 'vitest'
import {
  WORKER_PROTOCOL_VERSION,
  desktopToWorkerMessageSchema,
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

  it('parses an analyze request', () => {
    expect(
      desktopToWorkerMessageSchema.parse({
        type: 'recognition.analyze',
        schemaVersion: WORKER_PROTOCOL_VERSION,
        requestId: 'req-analyze',
        imagePath: 'C:/captures/shot.png',
        captureTimestamp: '2026-11-15T10:00:00.000Z',
        crop: { x: 0, y: 0.2, width: 0.16, height: 0.5 },
        catalogPath: 'C:/data/sets/set-18-ru.json',
      }).type,
    ).toBe('recognition.analyze')
  })

  it('rejects an analyze request with an out-of-range crop', () => {
    expect(
      desktopToWorkerMessageSchema.safeParse({
        type: 'recognition.analyze',
        schemaVersion: WORKER_PROTOCOL_VERSION,
        requestId: 'req-analyze',
        imagePath: 'C:/captures/shot.png',
        captureTimestamp: '2026-11-15T10:00:00.000Z',
        crop: { x: 0.9, y: 0.2, width: 0.16, height: 0.5 },
        catalogPath: 'C:/data/sets/set-18-ru.json',
      }).success,
    ).toBe(false)
  })

  it('parses a correlated recognition result', () => {
    const parsed = parseWorkerMessage(
      JSON.stringify({
        type: 'recognition.result',
        schemaVersion: WORKER_PROTOCOL_VERSION,
        requestId: 'req-analyze',
        captureTimestamp: '2026-11-15T10:00:00.000Z',
        setId: 'set-18',
        status: 'ok',
        traits: [
          {
            traitId: 'Inferno',
            displayName: 'Инферно',
            rawText: 'Инферно',
            count: 2,
            match: { method: 'exact', score: 1, margin: 0 },
          },
        ],
        unknownRows: [],
        diagnostics: {},
      }),
    )

    expect(parsed.type).toBe('recognition.result')
    if (parsed.type === 'recognition.result') {
      expect(parsed.requestId).toBe('req-analyze')
      expect(parsed.traits[0]?.count).toBe(2)
    }
  })
})
