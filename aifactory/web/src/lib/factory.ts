import { t } from './i18n'
import { factoryEn } from './i18n/factory'
import { ref } from 'vue'
import type { FactoryOptions, FactoryInitPlan, FactoryResult } from './api'
import { repoHref } from './router'

export function installOptions(plan: FactoryInitPlan): FactoryOptions {
  return { base: plan.base, provider: plan.provider,
    azure: { organization: '', project: '', repository: '', ...plan.azure },
    docs_root: plan.docs_root }
}

export const lastFactoryResult = ref<{ repoId: string; result: FactoryResult; action?: string } | null>(null)

/** Stable protocol codes; unknown actions stay visible for forward compatibility. */
export function planCodeText(code: string): string {
  const key = `factoryUi.plan.${code}` as keyof typeof factoryEn
  return key in factoryEn ? t(key) : code
}

export function fileActionText(action: string): string {
  const key = `factoryUi.file.${action}` as keyof typeof factoryEn
  return key in factoryEn ? t(key) : action
}

/** Opens the reviewed commit of .factory/ on the Factory screen (the config chip in the topbar). */
export function openConfigCommit(repoId: string): void {
  const href = repoHref(repoId, 'factory', 'config_commit')
  if (window.location.hash === href) window.dispatchEvent(new Event('factory-commit-preview'))
  else window.location.hash = href
}
