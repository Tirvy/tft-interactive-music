import { spawnSync } from 'node:child_process'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterAll, describe, expect, it } from 'vitest'
import type { WorkerStatus } from '@tft/shared-types/worker'
import { withSettingsDefaults } from '@tft/shared-types/settings'
import { Logger } from '../logger'
import { findRecognitionDir } from '../paths'
import { resolvePythonExecutable } from './python-resolver'
import { WorkerSupervisor } from './worker-supervisor'

const recognitionDir = findRecognitionDir([process.cwd()])
const python = recognitionDir
  ? resolvePythonExecutable(recognitionDir, process.env['TFT_TEST_PYTHON'] ?? null)
  : null
const pythonAvailable = python
  ? spawnSync(python.command, ['--version'], { encoding: 'utf8' }).status === 0
  : false

const temporaryDirectories: string[] = []
let supervisor: WorkerSupervisor | null = null

afterAll(() => {
  supervisor?.dispose()
  for (const directory of temporaryDirectories.splice(0)) {
    rmSync(directory, { recursive: true, force: true })
  }
})

const suite = recognitionDir && pythonAvailable ? describe : describe.skip

suite('WorkerSupervisor lifecycle', () => {
  it('starts, restarts, and stops the Python worker', async () => {
    const directory = mkdtempSync(join(tmpdir(), 'tft-worker-'))
    temporaryDirectories.push(directory)

    const statuses: WorkerStatus[] = []
    supervisor = new WorkerSupervisor({
      recognitionDir,
      logger: new Logger(join(directory, 'logs')),
      getSettings: () =>
        withSettingsDefaults({
          worker: {
            pythonPath: python?.command ?? null,
            autoStart: false,
            startupTimeoutMs: 15_000,
            heartbeatIntervalMs: 5000,
            heartbeatTimeoutMs: 15_000,
          },
        }),
      onStatus: (status) => {
        statuses.push(status)
      },
    })

    const starting = await supervisor.start()
    expect(['starting', 'running']).toContain(starting.state)

    const running = await waitFor(supervisor, (status) => status.state === 'running', 15_000)

    expect(running.pid).toBeGreaterThan(0)
    expect(running.workerVersion).toBe('0.2.0')
    expect(['stub', 'ocr']).toContain(running.mode)
    expect(running.lastError).toBeNull()

    await supervisor.restart()
    const restarted = await waitFor(supervisor, (status) => status.state === 'running', 15_000)
    expect(restarted.restartCount).toBe(1)

    const stopped = await supervisor.stop('test')
    expect(stopped.state).toBe('stopped')
    expect(stopped.pid).toBeNull()

    expect(statuses.some((status) => status.state === 'starting')).toBe(true)
    expect(statuses.some((status) => status.state === 'stopping')).toBe(true)
    expect(statuses.some((status) => status.state === 'stopped')).toBe(true)
  })
})

async function waitFor(
  workerSupervisor: WorkerSupervisor,
  predicate: (status: WorkerStatus) => boolean,
  timeoutMs: number,
): Promise<WorkerStatus> {
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    const status = workerSupervisor.getStatus()
    if (predicate(status)) {
      return status
    }
    await new Promise((resolve) => {
      setTimeout(resolve, 100)
    })
  }

  throw new Error(
    `Timed out waiting for worker status. Last: ${JSON.stringify(workerSupervisor.getStatus())}`,
  )
}
