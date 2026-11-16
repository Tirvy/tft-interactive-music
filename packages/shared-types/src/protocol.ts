import { z } from 'zod'
import { normalizedRectSchema } from './capture'
import { recognitionResultSchema } from './recognition'

/**
 * Version of the newline-delimited JSON protocol spoken over the worker's
 * stdio pipes. Bump this when a message shape changes incompatibly.
 */
export const WORKER_PROTOCOL_VERSION = 1

const schemaVersion = z.literal(WORKER_PROTOCOL_VERSION)

export const workerCapabilitiesSchema = z.object({
  mode: z.string().min(1),
  ocrEngine: z.string().min(1).nullable(),
  recognition: z.boolean(),
  liveCapture: z.boolean(),
})

export const workerReadyMessageSchema = z.object({
  type: z.literal('worker.ready'),
  schemaVersion,
  workerVersion: z.string().min(1),
  startedAt: z.string().min(1),
  capabilities: workerCapabilitiesSchema,
})

export const workerHeartbeatMessageSchema = z.object({
  type: z.literal('worker.heartbeat'),
  schemaVersion,
  sequence: z.number().int().nonnegative(),
  sentAt: z.string().min(1),
  uptimeMs: z.number().nonnegative(),
})

export const workerPongMessageSchema = z.object({
  type: z.literal('worker.pong'),
  schemaVersion,
  requestId: z.string().min(1),
  receivedAt: z.string().min(1),
})

export const workerStoppingMessageSchema = z.object({
  type: z.literal('worker.stopping'),
  schemaVersion,
  reason: z.string().nullable(),
})

export const workerErrorMessageSchema = z.object({
  type: z.literal('worker.error'),
  schemaVersion,
  code: z.string().min(1),
  message: z.string().min(1),
  detail: z.string().optional(),
  requestId: z.string().min(1).optional(),
})

/**
 * Result envelope for an analysis request. The body is the same versioned
 * recognition result the Python POC emits; the request id correlates the
 * response with its request over an async stdio channel.
 */
export const recognitionResultMessageSchema = recognitionResultSchema.extend({
  schemaVersion,
  requestId: z.string().min(1),
})

export const workerMessageSchema = z.discriminatedUnion('type', [
  workerReadyMessageSchema,
  workerHeartbeatMessageSchema,
  workerPongMessageSchema,
  workerStoppingMessageSchema,
  workerErrorMessageSchema,
  recognitionResultMessageSchema,
])

export const workerPingMessageSchema = z.object({
  type: z.literal('worker.ping'),
  schemaVersion,
  requestId: z.string().min(1),
  sentAt: z.string().min(1),
})

export const workerShutdownMessageSchema = z.object({
  type: z.literal('worker.shutdown'),
  schemaVersion,
  reason: z.string().min(1),
})

export const recognitionAnalyzeMessageSchema = z.object({
  type: z.literal('recognition.analyze'),
  schemaVersion,
  requestId: z.string().min(1),
  imagePath: z.string().min(1),
  captureTimestamp: z.string().min(1),
  crop: normalizedRectSchema,
  catalogPath: z.string().min(1),
  setId: z.string().min(1).optional(),
  preprocessMode: z.string().min(1).optional(),
  minConfidence: z.number().min(0).max(1).optional(),
  minOcrConfidence: z.number().min(0).max(1).optional(),
})

export const desktopToWorkerMessageSchema = z.discriminatedUnion('type', [
  workerPingMessageSchema,
  workerShutdownMessageSchema,
  recognitionAnalyzeMessageSchema,
])

export type WorkerCapabilities = z.infer<typeof workerCapabilitiesSchema>
export type WorkerReadyMessage = z.infer<typeof workerReadyMessageSchema>
export type WorkerHeartbeatMessage = z.infer<typeof workerHeartbeatMessageSchema>
export type WorkerPongMessage = z.infer<typeof workerPongMessageSchema>
export type WorkerStoppingMessage = z.infer<typeof workerStoppingMessageSchema>
export type WorkerErrorMessage = z.infer<typeof workerErrorMessageSchema>
export type WorkerMessage = z.infer<typeof workerMessageSchema>
export type WorkerPingMessage = z.infer<typeof workerPingMessageSchema>
export type WorkerShutdownMessage = z.infer<typeof workerShutdownMessageSchema>
export type RecognitionAnalyzeMessage = z.infer<typeof recognitionAnalyzeMessageSchema>
export type RecognitionResultMessage = z.infer<typeof recognitionResultMessageSchema>
export type DesktopToWorkerMessage = z.infer<typeof desktopToWorkerMessageSchema>

export function parseWorkerMessage(line: string): WorkerMessage {
  return workerMessageSchema.parse(JSON.parse(line))
}
