// Shared fixtures for the Backlog screen tests (same shapes as /api/backlog).
import type {
  BacklogData,
  ContainerDetail,
  ContainerDetailData,
  ContainerGraph,
  ContainerNode,
  RunCheck,
  RunStart,
  TaskDetail,
  TaskNode,
  TaskRun,
} from '@/lib/backlog'
import { TREE_EXPANDED_KEY, resetTreeForTests } from '@/lib/backlog'

/** Unfold every container of `backlogData()` (the tree starts folded). */
export function expandTree(keys: string[] = ['M01', 'M01-S01', 'M02', 'M02-S01']): void {
  localStorage.setItem(TREE_EXPANDED_KEY, JSON.stringify(keys))
  resetTreeForTests()
}

export function taskNode(over: Partial<TaskNode> = {}): TaskNode {
  return {
    kind: 'task',
    id: 'M01-S01-T02',
    title: 'Loader',
    level: 'task',
    path: 'backlog/M01-core/S01-model/M01-S01-T02-loader.md',
    status: 'todo',
    state: 'ready',
    workflow: 'plan-build',
    effective: { workflow: 'plan-build' },
    depends_on: ['M01-S01-T01'],
    related: [],
    writes: [],
    own_writes: [],
    blocked_by: [],
    blocks: ['M01-S01-T03'],
    board_state: 'ready',
    own_workflow: null,
    invalid: false,
    last_run: null,
    ...over,
  }
}

function container(over: Partial<ContainerNode>): ContainerNode {
  return {
    kind: 'container',
    id: 'M01',
    title: 'Core',
    level: 'module',
    path: 'backlog/M01-core',
    progress: { done: 0, total: 0 },
    done: false,
    blocks: [],
    children: [],
    can_toggle: true,
    effective_auto_continue: over.auto_continue === true,
    effective_auto_merge: over.auto_merge === true,
    ...over,
  }
}

export function backlogData(over: Partial<BacklogData> = {}): BacklogData {
  const t1 = taskNode({
    id: 'M01-S01-T01',
    title: 'Schema',
    status: 'done',
    state: 'done',
    board_state: 'done',
    depends_on: [],
    blocks: ['M01-S01-T02'],
  })
  const t2 = taskNode()
  const t3 = taskNode({
    id: 'M01-S01-T03',
    title: 'Writer',
    state: 'blocked',
    board_state: 'blocked',
    depends_on: ['M01-S01-T02'],
    blocked_by: [{ id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] }],
    blocks: [],
  })
  const b1 = taskNode({
    id: 'M02-S01-T01',
    title: 'Layout',
    workflow: null,
    board_state: 'todo',
    depends_on: [],
    blocks: [],
    path: 'backlog/M02-web/S01-ui/M02-S01-T01-layout.md',
  })
  const items = [
    container({
      progress: { done: 1, total: 3 },
      state_counts: { ready: 1, blocked: 1, done: 1 },
      children: [
        container({
          id: 'M01-S01',
          title: 'Model',
          level: 'step',
          path: 'backlog/M01-core/S01-model',
          progress: { done: 1, total: 3 },
          state_counts: { ready: 1, blocked: 1, done: 1 },
          auto_continue: true,
          children: [t1, t2, t3],
        }),
      ],
    }),
    container({
      id: 'M02',
      title: 'Web',
      path: 'backlog/M02-web',
      progress: { done: 0, total: 1 },
      state_counts: { todo: 1 },
      children: [
        container({
          id: 'M02-S01',
          title: 'UI',
          level: 'step',
          path: 'backlog/M02-web/S01-ui',
          progress: { done: 0, total: 1 },
          state_counts: { todo: 1 },
          children: [b1],
        }),
      ],
    }),
  ]
  return {
    levels: ['module', 'step', 'task'],
    backlog_dir: 'backlog',
    filters: { status: null },
    states: ['todo', 'ready', 'blocked', 'running', 'in review', 'done', 'cancelled'],
    workflows: ['custom-flow', 'plan', 'plan-build'],
    steps: [
      { id: 'M01-S01', title: 'Model', path: 'backlog/M01-core/S01-model', project: 'M01' },
      { id: 'M02-S01', title: 'UI', path: 'backlog/M02-web/S01-ui', project: 'M02' },
    ],
    items,
    tasks: [t1, t2, t3, b1],
    issues: [],
    counts: { module: 2, step: 2, task: 4 },
    ...over,
  }
}

export function taskDetail(over: Partial<TaskDetail> = {}): TaskDetail {
  return {
    task: taskNode({ related: ['M02-S01-T01'] }),
    body: '## Zadání\nNačíst backlog.\n',
    issues: [],
    runs: [
      {
        run_id: 'r-1',
        task_id: 'M01-S01-T02',
        branch: 'factory/M01-S01-T02-1',
        worktree: '/tmp/wt/r-1',
        base: 'main',
        base_sha: '0'.repeat(40),
        head_sha: null,
        state: 'succeeded',
        started_at: '2026-01-01T10:00:00+00:00',
        ended_at: '2026-01-01T10:05:00+00:00',
        pid: null,
        workflow: 'plan-build',
        note: null,
        error: null,
      },
    ],
    prs: [
      {
        branch: 'factory/M01-S01-T02-1',
        task_id: 'M01-S01-T02',
        provider: 'local',
        pr_id: '3',
        url: 'https://example.test/pr/3',
        base: 'main',
        base_sha: '0'.repeat(40),
        title: 'Loader',
        body: '',
        state: 'open',
        created_at: '2026-01-01T10:05:00+00:00',
        updated_at: '2026-01-01T10:05:00+00:00',
        merged_at: null,
        merge_sha: null,
      },
    ],
    depends: [{ id: 'M01-S01-T01', kind: 'task', title: 'Schema', state: 'done' }],
    blocks: [{ id: 'M01-S01-T03', title: 'Writer', board_state: 'blocked' }],
    ...over,
  }
}

export function taskRun(over: Partial<TaskRun> = {}): TaskRun {
  return {
    run_id: 'r-9',
    task_id: 'M01-S01-T02',
    branch: 'factory/M01-S01-T02-2',
    worktree: '/tmp/wt/r-9',
    base: 'main',
    base_sha: '0'.repeat(40),
    head_sha: null,
    state: 'running',
    started_at: '2026-01-02T10:00:00+00:00',
    ended_at: null,
    pid: 4242,
    workflow: 'plan-build',
    note: null,
    error: null,
    ...over,
  }
}

export function runCheck(over: Partial<RunCheck> = {}): RunCheck {
  return {
    task_id: 'M01-S01-T02',
    base: 'main',
    config: { base: 'main', commit: 'abcdef1234567890', clean: true, changes: [] },
    in_base: true,
    unmet: [],
    running: null,
    launcher_busy: false,
    ...over,
  }
}

export function runStart(over: Partial<RunStart> = {}): RunStart {
  return { task_id: 'M01-S01-T02', run: taskRun(), pending: false, force: false, ...over }
}

export function containerGraph(over: Partial<ContainerGraph> = {}): ContainerGraph {
  return {
    container: {
      id: 'M01-S01',
      title: 'Model',
      level: 'step',
      path: 'backlog/M01-core/S01-model',
      auto_continue: null,
      effective_auto_continue: false,
      can_toggle: true,
    },
    nodes: [
      { id: 'M01-S01-T01', title: 'Schema', kind: 'task', board_state: 'done', step: 'M01-S01', external: false },
      { id: 'M01-S01-T02', title: 'Loader', kind: 'task', board_state: 'ready', step: 'M01-S01', external: false },
      { id: 'M01-S01-T03', title: 'Writer', kind: 'task', board_state: 'blocked', step: 'M01-S01', external: false },
      { id: 'M02', title: 'Web', kind: 'container', board_state: null, state: '0/1', step: null, external: true },
    ],
    edges: [
      { from: 'M01-S01-T01', to: 'M01-S01-T02' },
      { from: 'M01-S01-T02', to: 'M01-S01-T03' },
      { from: 'M02', to: 'M01-S01-T03' },
    ],
    ...over,
  }
}

/** GET /api/backlog/containers/M01-S01: own workflow, the rest inherited or from config. */
export function containerDetail(over: Partial<ContainerDetail> = {}): ContainerDetailData {
  const step = { source: 'inherited', level: 'module', id: 'M01', path: 'backlog/M01-core/index.md' } as const
  return {
    container: {
      kind: 'container',
      id: 'M01-S01',
      title: 'Model',
      level: 'step',
      path: 'backlog/M01-core/S01-model',
      index_path: 'backlog/M01-core/S01-model/index.md',
      parent: 'M01',
      children: ['M01-S01-T01'],
      body: '# Model\n\nDatový **model**.<!-- skryté -->',
      own: { workflow: 'plan' },
      extra: {},
      effective: {
        workflow: {
          value: 'plan',
          origin: { source: 'own', level: 'step', id: 'M01-S01', path: 'backlog/M01-core/S01-model/index.md' },
        },
        writes: { value: ['src/'], origin: step },
        source: { value: null, origin: null },
        target: { value: null, origin: null },
        specs_dir: { value: 'specs', origin: { source: 'config', path: '.factory/config.yaml', key: 'specs_dir' } },
        docs_dir: { value: 'app_docs', origin: { source: 'config', path: '.factory/config.yaml', key: 'docs_dir' } },
        auto_continue: { value: false, origin: { source: 'default' } },
      },
      ...over,
    },
    editable_keys: ['workflow', 'writes', 'source', 'target', 'specs_dir', 'docs_dir', 'auto_continue'],
    issues: [],
  }
}
