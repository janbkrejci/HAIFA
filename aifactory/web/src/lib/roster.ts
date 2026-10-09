// Harness, model and thinking choices of the roster editor and the install form.
import type { FactoryRoster, MachineCheck, RosterPreset } from './api'

/** `harness/override.py THINKING_LEVELS`, used when the API sends none. */
export const THINKING_LEVELS: readonly string[] = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max']

/** `config/roster.py PRESETS`, used when the API sends none. */
export const DEFAULT_PRESETS: Readonly<Record<string, RosterPreset>> = {
  claude: { harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium' },
  codex: { harness: 'codex', model: 'gpt-6.1-sol', thinking: 'medium' },
}

/** Model names offered in the model fields (any other name can still be typed). */
export const MODEL_SUGGESTIONS: readonly string[] = modelSuggestions(DEFAULT_PRESETS, [])

export const PRESET_LABELS: Readonly<Record<string, string>> = { claude: 'Claude', codex: 'Codex' }

/** The preset models first, then the models the roster already uses, each once. */
export function modelSuggestions(presets: Readonly<Record<string, RosterPreset>>, used: readonly (string | null | undefined)[]): string[] {
  return [...new Set([...Object.values(presets).map((p) => p.model), ...used].filter((m): m is string => !!m))]
}

/** Presets and thinking levels of a roster answer, with the built-in defaults for an older API. */
export function rosterChoices(roster: FactoryRoster | null): { presets: Record<string, RosterPreset>; thinking: string[] } {
  const presets = roster?.presets && Object.keys(roster.presets).length ? roster.presets : { ...DEFAULT_PRESETS }
  const thinking = roster?.thinking_levels?.length ? roster.thinking_levels : [...THINKING_LEVELS]
  return { presets, thinking }
}

/** The harnesses the machine check knows (`harness_repos`), with a fallback for an older API. */
export function knownHarnesses(check: MachineCheck | null): string[] {
  const names = Object.keys(check?.harness_repos ?? {})
  return names.length ? names : ['claude', 'codex', 'pi']
}

/**
 * Harnesses installed and logged in on this machine: the known ones without a
 * `harness_missing` or `harness_login` finding of the machine check.
 */
export function detectedHarnesses(check: MachineCheck | null): string[] {
  if (!check) return []
  const broken = (name: string) =>
    check.findings.some(
      (f) =>
        (f.code === 'harness_missing' && f.message.startsWith(`harness ${name} `)) ||
        (f.code === 'harness_login' && f.message.startsWith(`${name} `)),
    )
  return knownHarnesses(check).filter((name) => !broken(name))
}
