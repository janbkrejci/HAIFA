import type { FactoryFile, PlanBlocker } from './api'
import type { LibraryPlan } from './library'

export interface OnboardingPlan {
  pending_pr?: { id: string; url: string }
  action: 'onboard' | 'adopt'; digest: string; base: string; base_sha?: string
  files?: FactoryFile[]; blockers?: PlanBlocker[]
  library?: { name: string; matches?: boolean }
  remote?: { name: string; url?: string | null } | null
  library_plan?: LibraryChanges | null; plan?: LibraryChanges | null
  manifest_library?: { name: string; remote?: string | null }
  report?: { code: string; subject: string; message: string; detail?: string; version?: string }[]
  items?: { type: string; name: string; state: string; adopt: string; fix?: string }[]
  warnings?: string[]; envelopeWarnings?: string[]
}
/** The library part of an onboarding plan: the same items and files as a library plan. */
export type LibraryChanges = Pick<LibraryPlan, 'items' | 'files'>
export function onboardingRequest(action: 'onboard' | 'adopt', target: 'base' | 'pr', digest?: string, message?: string) {
  return { action, options: {}, target: action === 'adopt' ? 'base' : target,
    ...(digest ? { digest } : {}), ...(action === 'onboard' && message ? { message } : {}) }
}
