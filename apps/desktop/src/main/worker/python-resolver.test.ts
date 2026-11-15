import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { resolvePythonExecutable } from './python-resolver'

describe('resolvePythonExecutable', () => {
  const recognitionDir = join('repo', 'apps', 'recognition')

  it('prefers an explicit settings path', () => {
    const resolved = resolvePythonExecutable(recognitionDir, 'C:\\Python\\python.exe', {
      platform: 'win32',
      exists: () => true,
    })

    expect(resolved).toEqual({ command: 'C:\\Python\\python.exe', origin: 'settings' })
  })

  it('prefers the Python 3.12 virtual environment on Windows', () => {
    const expected = join(recognitionDir, '.venv312', 'Scripts', 'python.exe')

    const resolved = resolvePythonExecutable(recognitionDir, null, {
      platform: 'win32',
      exists: (path) => path === expected,
    })

    expect(resolved).toEqual({ command: expected, origin: 'venv312' })
  })

  it('falls back to the older virtual environment', () => {
    const expected = join(recognitionDir, '.venv', 'Scripts', 'python.exe')

    const resolved = resolvePythonExecutable(recognitionDir, null, {
      platform: 'win32',
      exists: (path) => path === expected,
    })

    expect(resolved).toEqual({ command: expected, origin: 'venv' })
  })

  it('falls back to PATH when no virtual environment exists', () => {
    expect(
      resolvePythonExecutable(recognitionDir, null, {
        platform: 'win32',
        exists: () => false,
      }),
    ).toEqual({ command: 'python', origin: 'path' })
  })

  it('uses python3 on non-Windows platforms', () => {
    expect(
      resolvePythonExecutable(recognitionDir, null, {
        platform: 'linux',
        exists: () => false,
      }),
    ).toEqual({ command: 'python3', origin: 'path' })
  })
})
