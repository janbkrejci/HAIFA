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

const SKIP_LABELS: Record<string, string> = {
  writes_overlap: 'překryv writes',
  exclusive: 'jen samostatně',
  waits_on_pr: 'čeká na PR',
  blocked: 'blokováno',
  no_workflow: 'bez workflow',
  in_review: 'v review',
  running: 'běží',
  cannot_start: 'nelze spustit',
  excluded: 'odloženo v kanbanu',
}

export function skipReasonLabel(reason: string): string {
  return SKIP_LABELS[reason] ?? reason
}

const STOP_LABELS: Record<string, string> = {
  exhausted: 'není co spustit',
  failed: 'běh selhal',
  disabled: 'auto-continue vypnuto',
  not_merged: 'PR nesloučen',
}

/** The chain's state in the panel's header. */
export function chainStateLabel(chain: Chain): string {
  if (chain.state === 'running') return 'běží'
  if (chain.state === 'aborted') return 'přerušen'
  const stop = chain.stop ? (STOP_LABELS[chain.stop] ?? chain.stop) : '—'
  return `skončil: ${stop}`
}
