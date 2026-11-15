/// <reference types="vite/client" />

import type { TftApi } from '@tft/shared-types/ipc'

declare global {
  interface Window {
    tft: TftApi
  }
}

export {}
