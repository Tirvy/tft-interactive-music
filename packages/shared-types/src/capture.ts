import { z } from 'zod'

const unitFraction = z.number().min(0).max(1)

/** Rectangle stored relative to the captured source dimensions. */
export const normalizedRectSchema = z
  .object({
    x: unitFraction,
    y: unitFraction,
    width: z.number().gt(0).max(1),
    height: z.number().gt(0).max(1),
  })
  .refine((rect) => rect.x + rect.width <= 1 + 1e-9, {
    message: 'x + width must be at most 1',
    path: ['width'],
  })
  .refine((rect) => rect.y + rect.height <= 1 + 1e-9, {
    message: 'y + height must be at most 1',
    path: ['height'],
  })

export const captureSourceTypeSchema = z.enum(['screen', 'window'])

export const screenSizeSchema = z.object({
  width: z.number().int().nonnegative(),
  height: z.number().int().nonnegative(),
})

export const screenRectSchema = z.object({
  x: z.number().int(),
  y: z.number().int(),
  width: z.number().int().nonnegative(),
  height: z.number().int().nonnegative(),
})

export const captureDisplaySchema = z.object({
  id: z.string().min(1),
  label: z.string(),
  size: screenSizeSchema,
  workArea: screenRectSchema,
  physicalSize: screenSizeSchema,
  scaleFactor: z.number().positive(),
  rotation: z.number(),
  internal: z.boolean(),
})

export const captureSourceSchema = z.object({
  id: z.string().min(1),
  name: z.string(),
  type: captureSourceTypeSchema,
  displayId: z.string().nullable(),
  display: captureDisplaySchema.nullable(),
  thumbnailDataUrl: z.string().nullable(),
  appIconDataUrl: z.string().nullable(),
})

/** Upper bound for a single PNG payload crossing the IPC boundary. */
export const MAX_CAPTURE_BYTES = 32 * 1024 * 1024

export const saveCaptureRequestSchema = z.object({
  bytes: z
    .instanceof(Uint8Array)
    .refine((value) => value.byteLength > 0, 'capture frame is empty')
    .refine((value) => value.byteLength <= MAX_CAPTURE_BYTES, 'capture frame is too large'),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  sourceId: z.string().min(1),
  sourceName: z.string(),
  capturedAt: z.string().min(1),
  displayScaleFactor: z.number().positive().nullable(),
  sourceWidth: z.number().int().positive().nullable(),
  sourceHeight: z.number().int().positive().nullable(),
})

export const savedCaptureSchema = z.object({
  id: z.string().min(1),
  fileName: z.string().min(1),
  filePath: z.string().min(1),
  byteLength: z.number().int().positive(),
  width: z.number().int().positive(),
  height: z.number().int().positive(),
  sourceId: z.string().min(1),
  sourceName: z.string(),
  capturedAt: z.string().min(1),
  displayScaleFactor: z.number().positive().nullable(),
  sourceWidth: z.number().int().positive().nullable(),
  sourceHeight: z.number().int().positive().nullable(),
})

export type NormalizedRect = z.infer<typeof normalizedRectSchema>
export type CaptureSourceType = z.infer<typeof captureSourceTypeSchema>
export type ScreenSize = z.infer<typeof screenSizeSchema>
export type CaptureDisplay = z.infer<typeof captureDisplaySchema>
export type CaptureSource = z.infer<typeof captureSourceSchema>
export type SaveCaptureRequest = z.infer<typeof saveCaptureRequestSchema>
export type SavedCapture = z.infer<typeof savedCaptureSchema>
