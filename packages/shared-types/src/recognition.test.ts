import { describe, expect, it } from 'vitest'
import { recognitionResultSchema } from './recognition'

const sample = {
  type: 'recognition.result',
  schemaVersion: 1,
  captureTimestamp: '2026-11-15T10:00:00.000Z',
  setId: 'set-18',
  status: 'ok',
  traits: [
    {
      traitId: 'Inferno',
      displayName: 'Инферно',
      rawText: 'Инферно',
      count: 4,
      confidence: 0.97,
      match: { method: 'exact', score: 1, margin: 1 },
    },
  ],
  unknownRows: [],
  diagnostics: {
    ocrEngine: 'paddleocr',
    cropValid: true,
    source: { width: 1912, height: 1205 },
  },
}

describe('recognition result schema', () => {
  it('accepts the Python result contract', () => {
    expect(recognitionResultSchema.parse(sample).traits[0]?.count).toBe(4)
  })

  it('rejects a fractional count', () => {
    const result = recognitionResultSchema.safeParse({
      ...sample,
      traits: [{ ...sample.traits[0], count: 2.5 }],
    })

    expect(result.success).toBe(false)
  })

  it('rejects an unknown status', () => {
    expect(recognitionResultSchema.safeParse({ ...sample, status: 'stable' }).success).toBe(false)
  })
})
