import { computed, onMounted, ref } from 'vue'
import { getGlobal, postGlobal } from './api'

export interface HarnessSettings {
  version: number
  default_harness: string | null
  harnesses: Record<string, { enabled: boolean; model: string; thinking?: string | null }>
}
export interface HarnessCatalog {
  settings: HarnessSettings
  available: Record<string, boolean>
  models: Record<string, string[]>
  thinking_levels?: Record<string, Record<string, string[]>>
  thinking_defaults?: Record<string, Record<string, string | null>>
  configured: boolean
  tests?: Record<string, Record<string, HarnessTest>>
}
export interface HarnessTest { ok: boolean; error?: string | null; answer?: string; at?: string }
export const fetchHarnessSettings = () => getGlobal<HarnessCatalog>('/machine/harnesses')
export const saveHarnessSettings = (settings: HarnessSettings) => postGlobal<HarnessCatalog>('/machine/harnesses', settings)
export const testHarness = (harness: string, model: string, thinking?: string | null) => postGlobal<HarnessTest>('/machine/harnesses/test', { harness, model, ...(thinking ? { thinking } : {}) })

export function useHarnessChoices() {
  const catalog = ref<HarnessCatalog | null>(null)
  onMounted(async () => { try { const data = await fetchHarnessSettings(); if (data.settings?.harnesses) catalog.value = data } catch { /* Parent forms remain usable when the machine API is unavailable. */ } })
  const harnessOptions = computed(() => [
    { value: '', label: 'Zdědit' },
    ...Object.entries(catalog.value?.settings.harnesses ?? {}).filter(([name, c]) => c.enabled && catalog.value?.available[name]).map(([name]) => ({ value: name, label: name })),
  ])
  function modelOptions(harness?: string | null) {
    const selected = harness || catalog.value?.settings.default_harness || ''
    return [{ value: '', label: 'Zdědit' }, ...(catalog.value?.models[selected] ?? []).map(model => ({ value: model, label: model }))]
  }
  return { catalog, harnessOptions, modelOptions }
}
