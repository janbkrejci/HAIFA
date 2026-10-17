// The sample repository of `factory try` in the dashboard: "Vyzkoušet na ukázce" creates it
// (POST /api/demo), starts its first task with the first tested harness of this computer and
// opens its backlog; the run detail of the sample explains its steps; "Odebrat ukázku" removes it
// with its folder (DELETE /api/demo).
import { inject, ref, type InjectionKey, type Ref } from 'vue'
import { deleteGlobal, postGlobal } from './api'
import { RUN_HARNESSES } from './backlog'
import { errorText } from './format'
import { fetchHarnessSettings, type HarnessCatalog } from './machineHarnesses'
import type { PhaseDot, RunSummary } from './runs'

/** The first task of the sample's backlog: the one "Vyzkoušet na ukázce" starts. */
export const DEMO_TASK = 'DEMO-S01-T01'

export interface DemoCreated {
  path: string
  created: boolean
  registered: boolean
  repo_id: string
  base: string
  provider: string
}

export interface DemoRemoved {
  path: string
  repo_id: string | null
  deleted: boolean
}

export interface DemoHarness {
  harness: string
  model: string
}

/** What the last "Vyzkoušet na ukázce" did; the banner of the sample shows it. */
export interface DemoStart {
  repoId: string
  harness: DemoHarness | null
  runId: string | null
  /** The run could not be started (the sample itself exists then). */
  error: string | null
}

export const lastStart = ref<DemoStart | null>(null)

/**
 * The first harness with a successful test on this computer: the default harness first, then
 * claude, codex, pi; its chosen model when that one passed, else any model of it that passed.
 * Null when no enabled harness passed a test (the run then takes the repo's roster).
 */
export function firstTestedHarness(catalog: HarnessCatalog | null): DemoHarness | null {
  if (!catalog) return null
  const { settings, tests = {}, available = {} } = catalog
  const order = [...new Set([settings.default_harness, ...RUN_HARNESSES].filter((n): n is string => !!n))]
  const usable = order.filter((name) => settings.harnesses[name]?.enabled && available[name] !== false)
  for (const name of usable) {
    const model = settings.harnesses[name]?.model ?? ''
    if (model && tests[name]?.[model]?.ok === true) return { harness: name, model }
  }
  for (const name of usable) {
    const model = Object.entries(tests[name] ?? {}).find(([, test]) => test.ok === true)?.[0]
    if (model) return { harness: name, model }
  }
  return null
}

export function createDemo(): Promise<DemoCreated> {
  return postGlobal<DemoCreated>('/demo')
}

export function removeDemo(): Promise<DemoRemoved> {
  return deleteGlobal<DemoRemoved>('/demo')
}

/** Create the sample and start its first task; a failed start leaves the sample in place. */
export async function startDemo(): Promise<DemoStart> {
  const demo = await createDemo()
  let harness: DemoHarness | null = null
  try {
    harness = firstTestedHarness(await fetchHarnessSettings())
  } catch {
    // Without the computer's harnesses the run takes the repo's roster.
  }
  const result: DemoStart = { repoId: demo.repo_id, harness, runId: null, error: null }
  try {
    const started = await postGlobal<{ run: { run_id: string } | null }>(
      `/repos/${encodeURIComponent(demo.repo_id)}/backlog/tasks/${encodeURIComponent(DEMO_TASK)}/run`,
      harness ? { harness: harness.harness, model: harness.model } : {},
    )
    result.runId = started.run?.run_id ?? null
  } catch (err) {
    result.error = errorText(err)
  }
  lastStart.value = result
  return result
}

/** The folder of the open repo when it is the sample, else null (RepoScreen provides it). */
export const DEMO_REPO: InjectionKey<Ref<string | null>> = Symbol('demo-repo')

export function useDemoRepo(): Ref<string | null> {
  return inject(DEMO_REPO, ref(null))
}

export type DemoStepId = 'worktree' | 'build' | 'test' | 'review' | 'pr' | 'merge'
export type DemoStepState = 'done' | 'current' | 'todo'

export interface DemoStep {
  id: DemoStepId
  title: string
  text: string
  state: DemoStepState
}

const STEP_TEXT: readonly { id: DemoStepId; title: string; text: string }[] = [
  {
    id: 'worktree',
    title: 'Worktree',
    text: 'HAIFA založila pro běh vlastní větev a worktree. Tvůj checkout ukázky zůstává beze změny.',
  },
  {
    id: 'build',
    title: 'Build',
    text: 'Agent builder píše kód podle zadání tasku, jen do cest, které task povoluje.',
  },
  {
    id: 'test',
    title: 'Test',
    text: 'Tester naplánuje kontroly a HAIFA je spustí. Když neprojdou, builder opravuje, dokud nejsou zelené.',
  },
  {
    id: 'review',
    title: 'Review',
    text: 'Commit vznikne jen ze zeleného kódu. Workflow s reviewerem nechá změnu ještě posoudit agentem.',
  },
  {
    id: 'pr',
    title: 'PR',
    text: 'Hotová větev se publikuje jako pull request. Ukázka ho drží lokálně, bez GitHubu.',
  },
  {
    id: 'merge',
    title: 'Merge',
    text: 'PR schválíš v záložce Review a HAIFA ho sloučí do main. Tím je task hotový.',
  },
]

const OK = new Set(['success', 'succeeded', 'passed'])

function passed(phases: readonly PhaseDot[], test: (name: string) => boolean): boolean {
  return phases.some((p) => !!p.name && test(p.name) && OK.has(p.status ?? ''))
}

/**
 * The steps of the sample's run: done ones, the current one (while the run goes on or waits for
 * its PR) and the rest. A later step done makes every earlier one done.
 */
export function demoSteps(run: Pick<RunSummary, 'state' | 'pr'>, phases: readonly PhaseDot[]): DemoStep[] {
  const raw: Record<DemoStepId, boolean> = {
    worktree: phases.length > 0 || run.state !== 'running',
    build: passed(phases, (n) => n === 'build' || /^fix(_\d+)?$/.test(n)),
    test: passed(phases, (n) => /^test(_\d+)?$/.test(n)),
    review: passed(phases, (n) => /^review(_\d+)?$/.test(n)) || run.state === 'succeeded',
    pr: !!run.pr,
    merge: run.pr?.state === 'merged',
  }
  const done = STEP_TEXT.map((s) => raw[s.id])
  for (let i = done.length - 2; i >= 0; i--) done[i] = done[i] || done[i + 1]
  const goesOn = run.state === 'running' || run.state === 'succeeded'
  const current = goesOn ? done.indexOf(false) : -1
  return STEP_TEXT.map((s, i) => ({ ...s, state: done[i] ? 'done' : i === current ? 'current' : 'todo' }))
}

/** The sample went through the whole cycle: its PR is merged. */
export function demoFinished(run: Pick<RunSummary, 'pr'>): boolean {
  return run.pr?.state === 'merged'
}
