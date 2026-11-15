import { z } from 'zod'

export const recognitionStatusSchema = z.enum(['ok', 'partial', 'unavailable', 'error'])

export const traitMatchSchema = z.object({
  method: z.string().min(1),
  score: z.number(),
  margin: z.number(),
})

export const traitResultSchema = z.object({
  traitId: z.string().min(1),
  displayName: z.string().min(1),
  rawText: z.string(),
  count: z.number().int().nonnegative(),
  confidence: z.number().min(0).max(1).optional(),
  match: traitMatchSchema,
})

export const unknownRowSchema = z.object({
  rawText: z.string(),
  count: z.number().int().nonnegative().nullable(),
  reason: z.string().min(1),
  confidence: z.number().min(0).max(1).optional(),
  bbox: z.tuple([z.number(), z.number(), z.number(), z.number()]).optional(),
  candidateId: z.string().optional(),
  candidateDisplayName: z.string().optional(),
})

/**
 * Mirrors `apps/recognition/src/tft_recognition/result.py` schema version 1.
 * Keep this in sync with the Python result model when that contract changes.
 */
export const recognitionResultSchema = z.object({
  type: z.literal('recognition.result'),
  schemaVersion: z.literal(1),
  captureTimestamp: z.string().min(1),
  setId: z.string().min(1),
  status: recognitionStatusSchema,
  traits: z.array(traitResultSchema),
  unknownRows: z.array(unknownRowSchema),
  diagnostics: z.record(z.string(), z.unknown()),
})

export type RecognitionStatus = z.infer<typeof recognitionStatusSchema>
export type TraitMatch = z.infer<typeof traitMatchSchema>
export type TraitResult = z.infer<typeof traitResultSchema>
export type UnknownRow = z.infer<typeof unknownRowSchema>
export type RecognitionResult = z.infer<typeof recognitionResultSchema>
