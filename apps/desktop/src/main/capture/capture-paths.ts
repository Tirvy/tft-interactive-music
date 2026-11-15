import { isAbsolute, relative, resolve } from 'node:path'

/** Turn a source name into a short, filesystem-safe fragment. */
export function sanitizeFileNamePart(value: string, fallback = 'source'): string {
  const sanitized = value
    .normalize('NFKD')
    .replace(/[^\w.-]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '')
    .slice(0, 48)

  return sanitized.length > 0 ? sanitized : fallback
}

export function captureFileName(sourceName: string, capturedAt: string, id: string): string {
  const timestamp = capturedAt.replace(/[:.]/g, '-').replace(/[^\dTZ-]/g, '')
  const name = sanitizeFileNamePart(sourceName)
  return `tft-capture-${timestamp}-${name}-${id.slice(0, 8)}.png`
}

export function resolveCaptureDirectory(
  configuredDirectory: string | null,
  userDataPath: string,
): string {
  return configuredDirectory ? resolve(configuredDirectory) : resolve(userDataPath, 'captures')
}

/** True when `candidate` is a file or directory strictly inside `parent`. */
export function isPathInside(parent: string, candidate: string): boolean {
  const relativePath = relative(resolve(parent), resolve(candidate))
  return relativePath.length > 0 && !relativePath.startsWith('..') && !isAbsolute(relativePath)
}
