import { ref } from 'vue'
import type { FactoryOptions, FactoryInitPlan, AgentBinding, FactoryResult } from './api'

export function installOptions(plan: FactoryInitPlan): FactoryOptions {
  const bind: Record<string, AgentBinding> = {}
  for (const agent of plan.available?.agents ?? []) {
    bind[agent.name] = { harness: agent.harness, model: agent.model, thinking: agent.thinking }
  }
  Object.assign(bind, structuredClone(plan.bindings ?? {}))
  return { base: plan.base, provider: plan.provider,
    azure: { organization: '', project: '', repository: '', ...plan.azure },
    backlog_dir: plan.backlog_dir, specs_dir: plan.specs_dir, docs_dir: plan.docs_dir,
    agents: [...(plan.agents ?? [])], workflows: [...(plan.workflows ?? [])], bind }
}

export const lastFactoryResult = ref<{ repoId: string; result: FactoryResult; action?: string } | null>(null)

/** Plain-language texts of plan blocker and item codes; an unknown code shows as it is. */
const PLAN_CODE_TEXT: Record<string, string> = {
  library_missing: 'knihovna na tomto počítači chybí',
  library_mismatch: 'repo používá jinou knihovnu',
  plan_changed: 'plán se mezitím změnil',
  run_in_progress: 'v repu běží běhy',
  dirty_paths: 'necommitnuté změny v souborech factory',
  push_failed: 'push se nepodařil',
  base_behind: 'base je pozadu za remote',
  create: 'nová položka',
  add: 'přidání',
  update: 'aktualizace',
  remove: 'odebrání',
  unchanged: 'beze změny',
  import: 'import',
  new_item: 'nová položka',
  new_version: 'nová verze',
}

export function planCodeText(code: string): string {
  return PLAN_CODE_TEXT[code] ?? code
}

const FILE_ACTION_TEXT: Record<string, string> = { create: 'nový', modify: 'změna', delete: 'smazání' }

/** "nový / změna / smazání" of a planned file; an unknown action shows as it is. */
export function fileActionText(action: string): string {
  return FILE_ACTION_TEXT[action] ?? action
}
