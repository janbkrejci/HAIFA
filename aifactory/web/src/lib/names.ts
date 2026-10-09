// One shared map of project, step and task names (GET /api/repos/<id>/backlog/names) for the tooltips
// of codes on every screen. RepoScreen.vue loads it and reloads it on every live change of the
// backlog, so a renamed task shows its new title without reloading the page.
import { computed, ref } from 'vue'
import {
  DEFAULT_LEVELS,
  codeTooltip,
  fetchNames,
  levelsOf,
  type CodeName,
  type CodeNames,
} from './backlog'

const names = ref<CodeNames>({})
const levels = ref<string[]>([...DEFAULT_LEVELS])
let generation = 0

function isName(value: unknown): value is CodeName {
  if (typeof value !== 'object' || value === null) return false
  const v = value as Record<string, unknown>
  return typeof v.level === 'string' && (v.title === null || typeof v.title === 'string')
}

/** Replace the map with an answer of /api/backlog/names (malformed entries are dropped). */
export function setNames(data: { levels?: unknown; names?: unknown } | null | undefined): void {
  if (!data || typeof data !== 'object') return
  if (Array.isArray(data.levels)) levels.value = levelsOf(data.levels)
  const raw = data.names
  if (typeof raw !== 'object' || raw === null || Array.isArray(raw)) return
  const next: CodeNames = {}
  for (const [id, value] of Object.entries(raw as Record<string, unknown>)) {
    if (isName(value)) next[id] = { title: value.title, level: value.level }
  }
  names.value = next
}

/** Add or update names (e.g. from a freshly loaded backlog tree) without dropping others. */
export function mergeNames(entries: CodeNames): void {
  const changed = Object.entries(entries).some(
    ([id, n]) => names.value[id]?.title !== n.title || names.value[id]?.level !== n.level,
  )
  if (changed) names.value = { ...names.value, ...entries }
}

/** Set the configured `levels` (e.g. from /api/backlog or /api/review). */
export function setLevels(value: unknown): void {
  if (Array.isArray(value) && value.length) levels.value = levelsOf(value)
}

/** Reload the names; a failed load keeps the previous map. */
export async function refreshNames(): Promise<void> {
  const mine = ++generation
  try {
    const data = await fetchNames()
    if (mine === generation) setNames(data)
  } catch {
    // tooltips keep the last known names
  }
}

/** Tooltip of `id` from the shared map: `Task: <název>`, '' when unknown. */
export function nameTip(id: string | null | undefined): string {
  return codeTooltip(id, names.value)
}

/** The configured levels: all, the top one (project), the step and the task level. */
export function useLevels() {
  return {
    levels: computed(() => levels.value),
    top: computed(() => levels.value[0] ?? 'project'),
    step: computed(() => levels.value[levels.value.length - 2] ?? levels.value[0] ?? 'step'),
    task: computed(() => levels.value[levels.value.length - 1] ?? 'task'),
    containers: computed(() => levels.value.slice(0, -1)),
  }
}

export function useNames() {
  return {
    names: computed(() => names.value),
    levels: computed(() => levels.value),
    refresh: refreshNames,
    tip: nameTip,
  }
}

/** Forget every name and restore the default levels (a repo screen starts clean). */
export function resetNames(): void {
  generation += 1
  names.value = {}
  levels.value = [...DEFAULT_LEVELS]
}

/** Test helper: same as resetNames. */
export const resetNamesForTests = resetNames
