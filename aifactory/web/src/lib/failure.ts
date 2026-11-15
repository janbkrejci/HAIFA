import { t } from './i18n'
// The failure card of a run that did not succeed: the typed `failure_kind` of the run
// (`aifactory.failure`) in Czech, one sentence and the facts from `failure_detail`, and the
// actions that exist for the kind. Every text comes from the run's data, never a generic hint.

export type FailureKind =
  | 'accept_not_met'
  | 'nothing_to_do'
  | 'needs_environment'
  | 'quota'
  | 'writes_violation'
  | 'writes_needed'
  | 'invalid_output'
  | 'process_gone'
  | 'stopped'
  | 'blocked'
  | 'other'

/**
 * An action of the card: `continue` is `factory task retry`, `cancel_task` cancels the task,
 * `allow_writes` is `factory task retry --allow-writes` (add the paths to writes, continue;
 * for a ci-fix run `factory task approve --allow-writes`), after `writes_violation` or `writes_needed`,
 * `mark_done` marks the task of a `nothing_to_do` run done without changes (`POST /api/runs/{id}/done`),
 * `switch_harness` is `factory task retry --harness` on an enabled and tested harness.
 */
export type FailureAction = 'continue' | 'cancel_task' | 'allow_writes' | 'mark_done' | 'switch_harness'

const LABELS = (): Record<FailureKind, string> => ({
  accept_not_met: t('runs.nesplnena_podminka_accept'),
  nothing_to_do: t('runs.agent_nemel_co_delat'),
  needs_environment: t('runs.chybi_prostredi_pro_praci'),
  quota: t('runs.vycerpana_kvota'),
  writes_violation: t('runs.zapis_mimo_writes'),
  writes_needed: t('runs.chybi_cesty_ve_writes'),
  invalid_output: t('runs.neplatny_vystup_agenta'),
  process_gone: t('runs.proces_behu_skoncil'),
  stopped: t('runs.beh_zastaven'),
  blocked: t('runs.blokovany_233'),
  other: t('runs.jina_chyba'),
})

const ACTIONS: Record<FailureKind, readonly FailureAction[]> = {
  accept_not_met: ['continue', 'cancel_task'],
  nothing_to_do: ['mark_done', 'cancel_task'],
  needs_environment: ['continue', 'cancel_task'],
  quota: ['switch_harness', 'continue', 'cancel_task'],
  writes_violation: ['allow_writes', 'continue', 'cancel_task'],
  writes_needed: ['allow_writes', 'continue', 'cancel_task'],
  invalid_output: ['continue', 'cancel_task'],
  process_gone: ['continue', 'cancel_task'],
  stopped: ['continue', 'cancel_task'],
  blocked: ['continue', 'cancel_task'],
  other: ['continue', 'cancel_task'],
}

/** The kind of a run in Czech; an unknown kind unchanged, none: an empty string. */
export function failureLabel(kind: string | null | undefined): string {
  if (!kind) return ''
  return LABELS()[kind as FailureKind] ?? kind
}

/** One block of facts on the card: a heading and its lines. */
export interface FailureFact {
  /** Stable id for tests and styling: objections, checks, paths, writes, harness, … */
  id: string
  label: string
  items: string[]
  /** Paths, commands and expressions are shown in a monospace font. */
  mono?: boolean
  /** The items are task ids, shown as links to the tasks. */
  tasks?: boolean
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

const BLOCKED_PREFIX = 'blocked: '
const BLOCKED_WAITS = ' waits for '

/** The blockers named by a blocked run's error (`aifactory.failure.error_blockers`). */
export function errorBlockers(error: string | null | undefined): string[] {
  const text = error ?? ''
  if (!text.startsWith(BLOCKED_PREFIX)) return []
  const head = text.split(';', 1)[0] ?? ''
  const at = head.indexOf(BLOCKED_WAITS)
  if (at < 0) return []
  return head
    .slice(at + BLOCKED_WAITS.length)
    .split(', ')
    .map((part) => part.trim())
    .filter(Boolean)
}

/**
 * The kind of a run as shown: its `failure_kind`, else (a run recorded before the kinds)
 * `blocked` for an error starting with `blocked: ` and `other` for any ended unsuccessful run.
 */
export function shownFailureKind(run: { state: string | null; error?: string | null; failure_kind?: string | null }): string | null {
  if (run.state === 'running' || run.state === 'succeeded') return null
  if (run.failure_kind) return run.failure_kind
  if (!['failed', 'stopped', 'aborted'].includes(run.state ?? '')) return null
  return (run.error ?? '').startsWith(BLOCKED_PREFIX) ? 'blocked' : 'other'
}

/** The tasks a blocked run waits for; empty for any other run. */
export function runBlockers(run: FailedRun): string[] {
  if (shownFailureKind(run) !== 'blocked') return []
  const listed = strings(obj(run.failure_detail)?.blockers)
  return listed.length ? listed : errorBlockers(run.error)
}

function blockedCard(run: FailedRun): [string, FailureFact[]] {
  const blockers = runBlockers(run)
  const text = blockers.length
    ? t(blockers.length === 1 ? 'runs.blockedOne' : 'runs.blockedMany', { tasks: blockers.join(', ') })
    : t('runs.task_ceka_na_blokujici_tasky_po_jejich_dokonceni_se_da_pokracovat')
  return [text, blockers.length ? [{ id: 'blockers', label: t('runs.blokujici_tasky'), items: blockers, mono: true, tasks: true }] : []]
}

function acceptCard(run: FailedRun, d: Detail): [string, FailureFact[]] {
  const accept = str(d.accept)
  const error = firstLine(run.error)
  const text = error && error !== 'accept not met'
    ? error
    : accept ? t('runs.podminka_accept_p0_nebyla_splnena', { p0: accept }) : t('runs.podminka_accept_workflow_nebyla_splnena')
  const review = obj(d.review)
  const test = obj(d.test)
  const values = obj(d.values)
  const rounds = Array.isArray(d.rounds) ? d.rounds.map(obj).filter((r): r is Detail => r !== null) : []
  const facts = [
    ...fact(
      'objections',
      review ? t('runs.vytky_review_p0', { p0: str(review.step) ?? 'review' }) : t('runs.vytky_review'),
      review ? (strings(review.objections).length ? strings(review.objections) : [str(review.summary) ?? ''].filter(Boolean)) : [],
    ),
    ...fact('checks', test ? t('runs.neprosle_kontroly_p0', { p0: str(test.step) ?? 'test' }) : t('runs.neprosle_kontroly'), test ? strings(test.failed_checks) : [], true),
    ...fact('accept', t('runs.podminka_accept'), accept ? [accept] : [], true),
    ...fact('values', t('runs.hodnoty_v_podmince'), values ? Object.entries(values).map(([k, v]) => `${k} = ${shown(v)}`) : [], true),
    ...fact(
      'rounds',
      t('runs.kola_smycek'),
      rounds.map((r) => {
        const max = num(r.max)
        return `${str(r.loop) ?? 'repeat'}: ${num(r.rounds) ?? '?'}${max !== null ? t('runs.ofMax', { max }) : ''}`
      }),
      true,
    ),
  ]
  return [text, facts]
}

const ALLOW_REASONS = (): Record<string, string> => ({
  protected: t('runs.chranena_cesta_protected_files_writes_ji_nepovoli'),
  backlog: t('runs.backlogPath'),
  main_checkout: t('runs.zapis_do_hlavniho_checkoutu_mimo_worktree_behu_writes_ho_nepovoli'),
  already_allowed: t('runs.writes_tasku_ji_uz_povoluji_zapis_zakazaly_writes_agenta_agents_yaml'),
})

/** Why „Povolit tyto cesty a pokračovat“ does not add a path, in Czech. */
export function allowWritesReason(reason: string, message = ''): string {
  return ALLOW_REASONS()[reason] ?? (message || reason)
}

function writesCard(d: Detail): [string, FailureFact[]] {
  const agent = str(d.agent) ?? 'agent'
  const paths = [...strings(d.paths), ...strings(d.main_paths).map((p) => t('runs.hlavni_checkout_p0', { p0: p }))]
  const problems = strings(d.problems)
  const outside = paths.length ? paths : problems
  const n = outside.length
  const text = n
    ? t('runs.agent_p0_zapsal_mimo_povolene_cesty_p1_p2', { p0: agent, p1: n, p2: t('runs.pathCount', {}, n) })
    : t('runs.agent_p0_zapsal_mimo_povolene_cesty', { p0: agent })
  const writes = strings(d.writes)
  return [
    text,
    [
      ...fact('paths', t('runs.zapsano_mimo_writes'), outside, true),
      ...fact('writes', t('runs.povolene_writes'), writes, true),
    ],
  ]
}

/** The paths a `writes_needed` agent reported (`needs_writes`, else `paths`) with reasons. */
export function neededPaths(d: Detail): string[] {
  const items = Array.isArray(d.needs_writes) ? d.needs_writes.map(obj).filter((i): i is Detail => i !== null) : []
  const listed = items
    .map((i) => {
      const path = str(i.path)
      const reason = str(i.reason)
      return path ? (reason ? `${path} — ${reason}` : path) : null
    })
    .filter((p): p is string => p !== null)
  return listed.length ? listed : strings(d.paths)
}

function neededCard(d: Detail): [string, FailureFact[]] {
  const agent = str(d.agent) ?? 'agent'
  const paths = neededPaths(d)
  const n = paths.length
  const text = n
    ? t('runs.agent_p0_potrebuje_zmenit_cesty_mimo_writes_tasku_p1_p2', { p0: agent, p1: n, p2: t('runs.pathCount', {}, n) })
    : t('runs.agent_p0_potrebuje_zmenit_cesty_mimo_writes_tasku', { p0: agent })
  const summary = str(d.summary)
  return [
    text,
    [
      ...fact('paths', t('runs.potrebne_cesty'), paths, true),
      ...fact('summary', t('runs.zduvodneni_agenta'), summary ? [summary] : []),
    ],
  ]
}

function quotaCard(d: Detail, phases: readonly FailurePhase[]): [string, FailureFact[]] {
  const failed = [...phases].reverse().find((p) => p.status !== 'success' && (p.model || p.harness))
  const harness = str(d.harness) ?? str(failed?.harness) ?? 'harness'
  const model = str(d.model) ?? str(failed?.model)
  const agent = str(d.agent)
  const text = t('runs.harness_p0_ohlasil_vycerpanou_kvotu', { p0: harness }) + (model ? t('runs.quotaModel', { model }) : '') +
    (agent ? ` (agent ${agent})` : '')
  return [
    text,
    [
      ...fact('harness', 'Harness', [harness], true),
      ...fact('model', 'Model', model ? [model] : [], true),
      ...fact('message', t('runs.hlaska_harnessu'), str(d.message) ? [str(d.message) as string] : []),
    ],
  ]
}

function invalidCard(run: FailedRun, d: Detail): [string, FailureFact[]] {
  const agent = str(d.agent) ?? 'agent'
  if (d.cause === 'gates') {
    const violations = strings(d.violations)
    return [
      t('runs.vystup_agenta_p0_neprosel_kontrolami_ani_po_opravach', { p0: agent }),
      fact('violations', t('runs.neprosle_kontroly_vystupu'), violations),
    ]
  }
  if (d.cause === 'json') {
    const type = str(d.output_type)
    return [
      t('runs.agent_p0_nevratil_platny_json_p1', { p0: agent, p1: type ? ` ${type}` : '' }),
      fact('error', t('runs.chyba'), str(d.error) ? [str(d.error) as string] : [], true),
    ]
  }
  return [firstLine(run.error) ?? t('runs.agent_p0_nevratil_platny_vystup', { p0: agent }), []]
}

function stoppedText(run: FailedRun, d: Detail): string {
  if (d.cause === 'keyboard_interrupt') return t('runs.proces_behu_prerusil_ctrl_c')
  const signal = num(d.signal)
  if (d.cause === 'signal' && signal !== null) return t('runs.proces_behu_ukoncil_signal_p0', { p0: signal })
  const note = str(d.note) ?? firstLine(run.error)
  return note ? t('runs.beh_zastavil_operator_p0', { p0: note }) : t('runs.beh_zastavil_operator')
}

/** The card of a run that did not succeed; null for a running or succeeded run. */
export function failureCard(run: FailedRun, phases: readonly FailurePhase[] = []): FailureCard | null {
  const kind = shownFailureKind(run)
  if (!kind) return null
  const d = obj(run.failure_detail) ?? {}
  let text: string
  let facts: FailureFact[] = []
  switch (kind) {
    case 'accept_not_met':
      ;[text, facts] = acceptCard(run, d)
      break
    case 'nothing_to_do': {
      const summary = str(d.summary)
      text = t('runs.agent_p0_nemel_co_delat', { p0: str(d.agent) ?? 'agent' }) + (summary ? `: ${firstLine(summary)}` : '')
      break
    }
    case 'needs_environment': {
      text = t('runs.agent_p0_nema_prostredi_potrebne_pro_praci', { p0: str(d.agent) ?? 'agent' })
      const summary = str(d.summary)
      facts = fact('summary', t('runs.co_chybi_v_prostredi'), summary ? [summary] : [])
      break
    }
    case 'quota':
      ;[text, facts] = quotaCard(d, phases)
      break
    case 'writes_violation':
      ;[text, facts] = writesCard(d)
      break
    case 'writes_needed':
      ;[text, facts] = neededCard(d)
      break
    case 'invalid_output':
      ;[text, facts] = invalidCard(run, d)
      break
    case 'process_gone': {
      const pid = num(d.pid)
      text = pid !== null ? t('runs.proces_behu_pid_p0_skoncil_driv_nez_beh_dobehl', { p0: pid }) : (firstLine(run.error) ?? t('runs.proces_behu_skoncil_driv_nez_beh_dobehl'))
      break
    }
    case 'stopped':
      text = stoppedText(run, d)
      break
    case 'blocked':
      ;[text, facts] = blockedCard(run)
      break
    default:
      text = firstLine(run.error) ?? t('runs.beh_selhal_bez_chybove_zpravy')
  }
  return {
    kind,
    label: failureLabel(kind),
    sentence: sentence(text),
    facts,
    actions: ACTIONS[kind as FailureKind] ?? ACTIONS.other,
  }
}
