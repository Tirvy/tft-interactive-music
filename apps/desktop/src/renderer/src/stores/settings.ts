import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AppView, AppSettings, AppSettingsPatch } from '@tft/shared-types/settings'
import { DEFAULT_APP_SETTINGS } from '@tft/shared-types/settings'
import { errorMessage } from '../utils/errors'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>(DEFAULT_APP_SETTINGS)
  const loaded = ref(false)
  const error = ref<string | null>(null)

  async function load(): Promise<AppSettings> {
    try {
      settings.value = await window.tft.settings.get()
      loaded.value = true
      error.value = null
    } catch (cause) {
      error.value = errorMessage(cause)
    }

    return settings.value
  }

  async function update(patch: AppSettingsPatch): Promise<AppSettings> {
    try {
      settings.value = await window.tft.settings.update(patch)
      error.value = null
      return settings.value
    } catch (cause) {
      error.value = errorMessage(cause)
      throw cause
    }
  }

  return { settings, loaded, error, load, update }
})

export const useNavigationStore = defineStore('navigation', () => {
  const view = ref<AppView>('now-playing')

  function setView(next: AppView): void {
    view.value = next
  }

  return { view, setView }
})
