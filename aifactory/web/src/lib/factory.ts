import { ref } from 'vue'
import { removeRepo } from './api'
import type { FactoryOptions, FactoryInitPlan, AgentBinding, FactoryResult } from './api'
import { errorText } from './format'

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

// The App retains ownership while navigation waits for registry cleanup.
export const pendingInstall = ref<{ id: string; created: boolean } | null>(null)
export const lastFactoryResult = ref<{ repoId: string; result: FactoryResult; action?: string } | null>(null)
export const installRegistering = ref(false)
export const installBusy = ref(false)
export const installCancelling = ref(false)
export const installCancelError = ref<string | null>(null)
export async function cancelPendingInstall(): Promise<void> {
  if (installBusy.value || installCancelling.value) return
  installCancelling.value = true
  installCancelError.value = null
  try {
    if (pendingInstall.value?.created) await removeRepo(pendingInstall.value.id)
    pendingInstall.value = null
  } catch (e) {
    installCancelError.value = errorText(e)
  } finally { installCancelling.value = false }
}

/** Plain-language texts of plan blocker and item codes; an unknown code shows as it is. */
const PLAN_CODE_TEXT: Record<string, string> = {
  onboarded_in_remote: 'repo je už onboardované na remote',
  onboarding_pending: 'onboarding čeká v PR',
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
