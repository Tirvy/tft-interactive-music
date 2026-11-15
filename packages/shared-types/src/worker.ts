import { z } from 'zod'

export const workerStateSchema = z.enum([
  'stopped',
  'starting',
  'running',
  'stopping',
  'disconnected',
  'error',
])

export const workerErrorInfoSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  detail: z.string().optional(),
})

export const workerStatusSchema = z.object({
  state: workerStateSchema,
  pid: z.number().int().positive().nullable(),
  workerVersion: z.string().nullable(),
  mode: z.string().nullable(),
  pythonPath: z.string().nullable(),
  startedAt: z.string().nullable(),
  readyAt: z.string().nullable(),
  lastHeartbeatAt: z.string().nullable(),
  lastPongAt: z.string().nullable(),
  lastError: workerErrorInfoSchema.nullable(),
  restartCount: z.number().int().nonnegative(),
  updatedAt: z.string(),
})

export type WorkerState = z.infer<typeof workerStateSchema>
export type WorkerErrorInfo = z.infer<typeof workerErrorInfoSchema>
export type WorkerStatus = z.infer<typeof workerStatusSchema>

export function createInitialWorkerStatus(now = new Date().toISOString()): WorkerStatus {
  return {
    state: 'stopped',
    pid: null,
    workerVersion: null,
    mode: null,
    pythonPath: null,
    startedAt: null,
    readyAt: null,
    lastHeartbeatAt: null,
    lastPongAt: null,
    lastError: null,
    restartCount: 0,
    updatedAt: now,
  }
}
