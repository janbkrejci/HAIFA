import { t } from './i18n'
// Auto-continue chains (GET /api/chains): runs of a chain with their results, free slots of
// max_parallel_runs, tasks the last selection skipped and why, tasks that ran alone (wide
// writes). POST /api/chains/<id>/dismiss erases an ended chain.
import { getApi, postApi } from './api'
import type { RunPause } from './runs'

export interface ChainSkip {
  task_id: string
  reason: string
  detail: string
  waits_on: string[]
}

export interface ChainRunPr {
  url: string
  pr_id: string
  state: string
  merged_by?: string | null
  auto_merge_error?: string | null
}

export interface ChainRun {
  run_id: string
  task_id: string | null
  state: string | null
  workflow?: string | null
  error?: string | null
  /** The typed kind of a run that did not succeed (`aifactory.failure`). */
  failure_kind?: string | null
  /** A running run's pause: 'pausing' (asked for) or 'paused' (waits before its next phase). */
  pause?: RunPause | null
  /** The run's pull request and what auto-merge did with it. */
  pr?: ChainRunPr | null
}

export interface Chain {
  chain_id: string
  task_id: string
  state: string
  stop: string | null
  max_parallel: number
  started_at: string
  updated_at: string
  ended_at: string | null
  runs: ChainRun[]
  running: number
  /** Tasks whose open PR waits for review and holds a slot (empty once the chain ended). */
  in_review?: string[]
  free_slots: number
  skipped: ChainSkip[]
  exclusive: string[]
}

export interface ChainsResponse {
  max_parallel_runs: number | null
  chains: Chain[]
}

export function fetchChains(): Promise<ChainsResponse> {
  return getApi<ChainsResponse>('/chains')
}

/** Erase an ended chain from the panel; its runs stay. */
export function dismissChain(chainId: string): Promise<{ dismissed: string }> {
  return postApi<{ dismissed: string }>(`/chains/${encodeURIComponent(chainId)}/dismiss`)
}

/** The first line of a run's error, for one row of the panel (the whole text in a tooltip). */
export function firstLine(text: string): string {
  return text.split('\n', 1)[0] ?? ''
}

/** The chains of any reply; anything that is not a list gives none. */
export function chainsOf(data: unknown): Chain[] {
  if (typeof data !== 'object' || data === null) return []
  const chains = (data as { chains?: unknown }).chains
  return Array.isArray(chains) ? (chains as Chain[]) : []
}

const SKIP_LABELS = (): Record<string, string> => ({
  writes_overlap: t('runs.prekryv_writes'),
  exclusive: t('runs.jen_samostatne'),
  waits_on_pr: t('runs.ceka_na_pr'),
  blocked: t('runs.blokovano'),
  no_workflow: t('runs.noWorkflow'),
  human_task: t('runs.pro_cloveka'),
  in_review: t('runs.inReview'),
  no_slot: t('runs.zadny_volny_slot_pr_v_review'),
  running: t('runs.bezi_169'),
  cannot_start: t('runs.cannotStart'),
  excluded: t('runs.odlozeno_v_kanbanu'),
})

export function skipReasonLabel(reason: string): string {
  return SKIP_LABELS()[reason] ?? reason
}

const STOP_LABELS = (): Record<string, string> => ({
  exhausted: t('runs.neni_co_spustit'),
  failed: t('runs.beh_selhal'),
  disabled: t('runs.autoDisabled'),
  not_merged: t('runs.pr_nesloucen'),
})

/** The chain's state in the panel's header. */
export function chainStateLabel(chain: Chain): string {
  if (chain.state === 'running') return t('runs.bezi_169')
  if (chain.state === 'aborted') return t('runs.prerusen')
  const stop = chain.stop ? (STOP_LABELS()[chain.stop] ?? chain.stop) : '—'
  return t('runs.skoncil_p0', { p0: stop })
}
