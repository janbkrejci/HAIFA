// Session limits of the Claude and Codex subscriptions: on a repo page those its harnesses use
// plus the ones this machine has (/api/repos/<id>/limits), elsewhere the machine's (/api/limits).
// The 5-hour and the weekly window, shown small in the topbar.
import { onBeforeUnmount, onMounted, ref, watch, type Ref } from 'vue'
import { getGlobal } from './api'
import { fmtDayTime } from './format'
import { currentRepoId, useRepoId } from './router'
import { fetchHarnessSettings } from './machineHarnesses'

export interface LimitWindow {
  id: '5h' | '1w'
  label: string
  /** Used share of the window, 0–100. */
  used: number
  /** Share still free, 0–100. */
  left: number
  resets_at: string | null
}

export interface LimitProvider {
  harness: string
  label: string
  /** Empty when the limits were never measured. */
  windows: LimitWindow[]
  /** Why the last read failed; the windows are then the last measured ones (`stale`). */
  error: string | null
  /** When the windows were measured. */
  measured_at?: string | null
  stale?: boolean
}

export interface Limits {
  providers: LimitProvider[]
}

/** The limits of repo `repo`, or of this machine without one. */
export function fetchLimits(repo: string | null = null): Promise<Limits> {
  return getGlobal<Limits>(repo === null ? '/limits' : `/repos/${encodeURIComponent(repo)}/limits`)
}

export const LIMITS_POLL_MS = 60_000

/** Whole percent, clamped to 0–100. */
export function pct(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)))
}

/** "zbývá 30 % · obnoví se 4. 10. 12:00" for the tooltip of one window; stale ones say when measured. */
export function windowTip(provider: LimitProvider, window: LimitWindow): string {
  const name = window.id === '5h' ? '5hodinový limit' : 'týdenní limit'
  let text = `${provider.label}, ${name}: zbývá ${pct(window.left)} %, využito ${pct(window.used)} %`
  const resets = fmtDayTime(window.resets_at)
  if (resets) text += ` · obnoví se ${resets}`
  if (provider.stale) {
    text += ' · zastaralé údaje'
    const measured = fmtDayTime(provider.measured_at)
    if (measured) text += ` · naposledy změřeno ${measured}`
    if (provider.error) text += ` (${provider.error})`
  }
  return text
}

export function unavailableTip(provider: LimitProvider): string {
  return `${provider.label}: limity nedostupné · ${provider.error || 'aktuální limity nebyly změřeny'}${provider.harness === 'codex' ? ' · ověřte codex login a instalaci Codex CLI' : ''}`
}

/**
 * Polls the limits of the repo in the URL; a failed request keeps the last known limits.
 * `repo` null (off a repo page, or an unknown repo) polls the machine's limits instead.
 * A switch of the repo drops the old ones and loads anew.
 */
export function useLimits(repo: Ref<string | null> = useRepoId()) {
  const providers = ref<LimitProvider[]>([])
  const loading = ref(true)
  const usable = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null
  let generation = 0

  async function refresh(): Promise<void> {
    const mine = ++generation
    const id = repo.value !== null && repo.value === currentRepoId() ? repo.value : null
    try {
      const [limits, catalog] = await Promise.all([
        fetchLimits(id).catch(() => null), fetchHarnessSettings().catch(() => null),
      ])
      if (mine === generation) {
        providers.value = limits?.providers ?? providers.value.map(p => ({ ...p, stale: true, error: 'dashboard nemohl načíst limity' }))
        usable.value = catalog?.settings?.harnesses
          ? Object.entries(catalog.settings.harnesses).some(([name, choice]) =>
            choice.enabled && catalog.available[name] && !!choice.model && catalog.tests?.[name]?.[choice.model]?.ok !== false)
          : providers.value.length > 0
      }
    } catch {
      if (mine === generation) {
        providers.value = providers.value.map((p) => ({ ...p, stale: true, error: 'dashboard nemohl načíst limity' }))
      }
    } finally { if (mine === generation) loading.value = false }
  }

  watch(repo, () => {
    providers.value = []
    loading.value = true
    void refresh()
  })

  onMounted(() => {
    void refresh()
    timer = setInterval(() => void refresh(), LIMITS_POLL_MS)
  })
  onBeforeUnmount(() => {
    if (timer !== null) clearInterval(timer)
  })

  return { providers, loading, usable, refresh }
}
