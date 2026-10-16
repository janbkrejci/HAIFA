// The failure card of a run that did not succeed: the typed `failure_kind` of the run
// (`aifactory.failure`) in Czech, one sentence and the facts from `failure_detail`, and the
// actions that exist for the kind. Every text comes from the run's data, never a generic hint.
import { plural } from './format'

export type FailureKind =
  | 'accept_not_met'
  | 'nothing_to_do'
  | 'quota'
  | 'writes_violation'
  | 'invalid_output'
  | 'process_gone'
  | 'stopped'
  | 'other'

/**
 * An action of the card: `continue` is `factory task retry`, `cancel_task` cancels the task,
 * `allow_writes` is `factory task retry --allow-writes` (add the paths to writes, continue),
 * `mark_done` marks the task of a `nothing_to_do` run done without changes (`POST /api/runs/{id}/done`).
 */
export type FailureAction = 'continue' | 'cancel_task' | 'allow_writes' | 'mark_done'

const LABELS: Record<FailureKind, string> = {
  accept_not_met: 'Nesplněná podmínka accept',
  nothing_to_do: 'Agent neměl co dělat',
  quota: 'Vyčerpaná kvóta',
  writes_violation: 'Zápis mimo writes',
  invalid_output: 'Neplatný výstup agenta',
  process_gone: 'Proces běhu skončil',
  stopped: 'Běh zastaven',
  other: 'Jiná chyba',
}

// S02 adds more (continue on a fallback harness).
const ACTIONS: Record<FailureKind, readonly FailureAction[]> = {
  accept_not_met: ['continue', 'cancel_task'],
  nothing_to_do: ['mark_done', 'cancel_task'],
  quota: ['continue', 'cancel_task'],
  writes_violation: ['allow_writes', 'continue', 'cancel_task'],
  invalid_output: ['continue', 'cancel_task'],
  process_gone: ['continue', 'cancel_task'],
  stopped: ['continue', 'cancel_task'],
  other: ['continue', 'cancel_task'],
}

/** The kind of a run in Czech; an unknown kind unchanged, none: an empty string. */
export function failureLabel(kind: string | null | undefined): string {
  if (!kind) return ''
  return LABELS[kind as FailureKind] ?? kind
}

/** One block of facts on the card: a heading and its lines. */
export interface FailureFact {
  /** Stable id for tests and styling: objections, checks, paths, writes, harness, … */
  id: string
  label: string
  items: string[]
  /** Paths, commands and expressions are shown in a monospace font. */
  mono?: boolean
}

export interface FailureCard {
  kind: string
  label: string
  sentence: string
  facts: FailureFact[]
  actions: readonly FailureAction[]
}

/** What the card reads from a run (a run summary of the detail). */
export interface FailedRun {
  state: string | null
  error: string | null
  failure_kind?: string | null
  failure_detail?: Record<string, unknown> | null
}

/** A phase of the run, for the model of a quota failure recorded without one. */
export interface FailurePhase {
  status: string | null
  harness?: string | null
  model?: string | null
}

type Detail = Record<string, unknown>

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function obj(value: unknown): Detail | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Detail) : null
}

function strings(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string' && !!v.trim()) : []
}

function firstLine(text: string | null): string | null {
  const line = text?.trim().split('\n', 1)[0]?.trim()
  return line ? line : null
}

function sentence(text: string): string {
  const t = text.trim()
  return /[.!?…:]$/.test(t) ? t : `${t}.`
}

function shown(value: unknown): string {
  if (value === null || value === undefined) return 'null'
  if (typeof value === 'string') return `'${value}'`
  return String(value)
}

function fact(id: string, label: string, items: string[], mono = false): FailureFact[] {
  return items.length ? [{ id, label, items, mono }] : []
}

function acceptCard(run: FailedRun, d: Detail): [string, FailureFact[]] {
  const accept = str(d.accept)
  const error = firstLine(run.error)
  const text = error && error !== 'accept not met'
    ? error
    : accept ? `Podmínka accept \`${accept}\` nebyla splněna` : 'Podmínka accept workflow nebyla splněna'
  const review = obj(d.review)
  const test = obj(d.test)
  const values = obj(d.values)
  const rounds = Array.isArray(d.rounds) ? d.rounds.map(obj).filter((r): r is Detail => r !== null) : []
  const facts = [
    ...fact(
      'objections',
      review ? `Výtky review (${str(review.step) ?? 'review'})` : 'Výtky review',
      review ? (strings(review.objections).length ? strings(review.objections) : [str(review.summary) ?? ''].filter(Boolean)) : [],
    ),
    ...fact('checks', test ? `Neprošlé kontroly (${str(test.step) ?? 'test'})` : 'Neprošlé kontroly', test ? strings(test.failed_checks) : [], true),
    ...fact('accept', 'Podmínka accept', accept ? [accept] : [], true),
    ...fact('values', 'Hodnoty v podmínce', values ? Object.entries(values).map(([k, v]) => `${k} = ${shown(v)}`) : [], true),
    ...fact(
      'rounds',
      'Kola smyček',
      rounds.map((r) => {
        const max = num(r.max)
        return `${str(r.loop) ?? 'repeat'}: ${num(r.rounds) ?? '?'}${max !== null ? ` z ${max}` : ''}`
      }),
      true,
    ),
  ]
  return [text, facts]
}

const ALLOW_REASONS: Record<string, string> = {
  protected: 'chráněná cesta (protected_files), writes ji nepovolí',
  backlog: 'cesta v backlogu, backlog zapisuje jen factory',
  main_checkout: 'zápis do hlavního checkoutu mimo worktree běhu, writes ho nepovolí',
  already_allowed: 'writes tasku ji už povolují, zápis zakázaly writes agenta (agents.yaml)',
}

/** Why „Povolit tyto cesty a pokračovat“ does not add a path, in Czech. */
export function allowWritesReason(reason: string, message = ''): string {
  return ALLOW_REASONS[reason] ?? (message || reason)
}

function writesCard(d: Detail): [string, FailureFact[]] {
  const agent = str(d.agent) ?? 'agent'
  const paths = [...strings(d.paths), ...strings(d.main_paths).map((p) => `hlavní checkout: ${p}`)]
  const problems = strings(d.problems)
  const outside = paths.length ? paths : problems
  const n = outside.length
  const text = n
    ? `Agent ${agent} zapsal mimo povolené cesty (${n} ${plural(n, 'cesta', 'cesty', 'cest')})`
    : `Agent ${agent} zapsal mimo povolené cesty`
  const writes = strings(d.writes)
  return [
    text,
    [
      ...fact('paths', 'Zapsáno mimo writes', outside, true),
      ...fact('writes', 'Povolené writes', writes, true),
    ],
  ]
}

function quotaCard(d: Detail, phases: readonly FailurePhase[]): [string, FailureFact[]] {
  const failed = [...phases].reverse().find((p) => p.status !== 'success' && (p.model || p.harness))
  const harness = str(d.harness) ?? str(failed?.harness) ?? 'harness'
  const model = str(d.model) ?? str(failed?.model)
  const agent = str(d.agent)
  const text = `Harness ${harness} ohlásil vyčerpanou kvótu` + (model ? ` u modelu ${model}` : '') +
    (agent ? ` (agent ${agent})` : '')
  return [
    text,
    [
      ...fact('harness', 'Harness', [harness], true),
      ...fact('model', 'Model', model ? [model] : [], true),
      ...fact('message', 'Hláška harnessu', str(d.message) ? [str(d.message) as string] : []),
    ],
  ]
}

function invalidCard(run: FailedRun, d: Detail): [string, FailureFact[]] {
  const agent = str(d.agent) ?? 'agent'
  if (d.cause === 'gates') {
    const violations = strings(d.violations)
    return [
      `Výstup agenta ${agent} neprošel kontrolami ani po opravách`,
      fact('violations', 'Neprošlé kontroly výstupu', violations),
    ]
  }
  if (d.cause === 'json') {
    const type = str(d.output_type)
    return [
      `Agent ${agent} nevrátil platný JSON${type ? ` ${type}` : ''}`,
      fact('error', 'Chyba', str(d.error) ? [str(d.error) as string] : [], true),
    ]
  }
  return [firstLine(run.error) ?? `Agent ${agent} nevrátil platný výstup`, []]
}

function stoppedText(run: FailedRun, d: Detail): string {
  if (d.cause === 'keyboard_interrupt') return 'Proces běhu přerušil Ctrl+C'
  const signal = num(d.signal)
  if (d.cause === 'signal' && signal !== null) return `Proces běhu ukončil signál ${signal}`
  const note = str(d.note) ?? firstLine(run.error)
  return note ? `Běh zastavil operátor: ${note}` : 'Běh zastavil operátor'
}

/** The card of a run that did not succeed; null for a running or succeeded run. */
export function failureCard(run: FailedRun, phases: readonly FailurePhase[] = []): FailureCard | null {
  const kind = run.failure_kind ?? (['failed', 'stopped', 'aborted'].includes(run.state ?? '') ? 'other' : null)
  if (!kind || run.state === 'running' || run.state === 'succeeded') return null
  const d = obj(run.failure_detail) ?? {}
  let text: string
  let facts: FailureFact[] = []
  switch (kind) {
    case 'accept_not_met':
      ;[text, facts] = acceptCard(run, d)
      break
    case 'nothing_to_do': {
      const summary = str(d.summary)
      text = `Agent ${str(d.agent) ?? 'agent'} neměl co dělat` + (summary ? `: ${firstLine(summary)}` : '')
      break
    }
    case 'quota':
      ;[text, facts] = quotaCard(d, phases)
      break
    case 'writes_violation':
      ;[text, facts] = writesCard(d)
      break
    case 'invalid_output':
      ;[text, facts] = invalidCard(run, d)
      break
    case 'process_gone': {
      const pid = num(d.pid)
      text = pid !== null ? `Proces běhu (PID ${pid}) skončil dřív, než běh doběhl` : (firstLine(run.error) ?? 'Proces běhu skončil dřív, než běh doběhl')
      break
    }
    case 'stopped':
      text = stoppedText(run, d)
      break
    default:
      text = firstLine(run.error) ?? 'Běh selhal bez chybové zprávy'
  }
  return {
    kind,
    label: failureLabel(kind),
    sentence: sentence(text),
    facts,
    actions: ACTIONS[kind as FailureKind] ?? ACTIONS.other,
  }
}
