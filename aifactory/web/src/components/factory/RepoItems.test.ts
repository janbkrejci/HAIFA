import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoItems from './RepoItems.vue'
import { answerDialog, openDialog } from '@/test/modal'

enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

const items = [
  { type: 'agent', name: 'builder', origin: 'library' },
  { type: 'agent', name: 'mine', origin: 'repo' },
  { type: 'skill', name: 'lint', origin: 'library' },
  { type: 'workflow', name: 'mine-flow', origin: 'repo' },
]
const SHA = 'aa8e9808b9a3a45697b65223d019063bd4e3e289'
const roster = {
  agents: [
    { name: 'builder', harness: 'claude', model: 'opus', thinking: 'medium', origin: 'library', overridden: [],
      inherited: { harness: 'claude', model: 'opus', thinking: 'medium' } },
    { name: 'mine', harness: 'codex', model: 'gpt-6.1-sol', thinking: 'high', origin: 'repo', overridden: ['harness'], inherited: null },
  ],
  workflow_tasks: {}, presets: {}, thinking_levels: ['medium', 'high'], workflow_overrides: [],
}
const plan = {
  action: 'move', repo: '/w/repo', command: 'move', type: 'agent', name: 'mine', base: 'main', base_sha: 'abc', target: 'base',
  files: [{ path: '.factory/agents/mine/agent.md', action: 'delete', diff: '-old', content: null, binary: false }],
  blockers: [], digest: 'move-digest', warnings: [], library: '0123456789',
  library_plan: { digest: 'lib', files: [{ path: 'agents/mine/agent.md', action: 'create', diff: '', content: 'new', binary: false }] },
}

function stub(movePlan: unknown = plan, library: { library: string | null; library_name?: string | null } = { library: SHA, library_name: 'team' }) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/repos/a/factory/items') return ok({ ...library, items })
    if (url === '/api/repos/a/factory/roster') return ok(roster)
    if (url === '/api/machine/check') return ok({ findings: [] })
    if (url === '/api/repos/a/factory/plan') return ok(movePlan)
    if (url === '/api/repos/a/factory/apply') return ok({ commit: 'c1', library_commit: 'feedbeef99', pushed: false })
    throw new Error(`unexpected ${url} ${init?.method}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const mountItems = () => mount(RepoItems, { props: { repoId: 'a' }, attachTo: document.body })

describe('RepoItems', () => {
  it('is Vybavení továrny with every agent once and the move only for an own copy', async () => {
    stub()
    const w = mountItems(); await flushPromises()
    expect(w.get('h2').text()).toBe('Vybavení továrny')
    expect(w.findAll('[data-test="roster-agent-builder"]')).toHaveLength(1)
    expect(w.findAll('[data-test="roster-agent-mine"]')).toHaveLength(1)
    expect(w.find('[data-test="item-agent-builder"]').exists()).toBe(false)
    expect(w.get('[data-test="roster-agent-builder"]').text()).toContain('z knihovny')
    expect(w.get('[data-test="roster-agent-mine"]').text()).toContain('vlastní kopie')
    expect(w.get('[data-test="items-agent"] h3').text()).toBe('Agenti (2)')
    expect(w.get('[data-test="item-skill-lint"]').text()).toContain('z knihovny')
    expect(w.get('[data-test="item-workflow-mine-flow"]').text()).toContain('vlastní kopie')
    expect(w.find('[data-test="item-move-workflow-mine-flow"]').exists()).toBe(true)
    expect(w.find('[data-test="item-move-agent-builder"]').exists()).toBe(false)
    expect(w.find('[data-test="item-move-agent-mine"]').exists()).toBe(true)
    expect(w.find('[data-test="items-extension"]').text()).toContain('Bez položek')
  })

  it('names the library and its short commit, with a space and no full SHA', async () => {
    stub()
    const w = mountItems(); await flushPromises()
    const hint = w.get('[data-test="items-inherit"]').text()
    expect(hint).toBe('Bez vlastní kopie v .factory/ se položka dědí z knihovny „team“ (aa8e980).')
    expect(w.text()).not.toContain(SHA)
    expect(w.text()).not.toContain('knihovnyaa8e')
  })

  it('names the built-in set without a library', async () => {
    stub(plan, { library: null })
    const w = mountItems(); await flushPromises()
    expect(w.get('[data-test="items-inherit"]').text()).toContain('vestavěné výchozí sady')
  })

  it('previews the move, applies the reviewed digest after confirmation and reloads', async () => {
    const fetchMock = stub()
    const w = mountItems(); await flushPromises()
    await w.get('[data-test="item-move-agent-mine"]').trigger('click'); await flushPromises()
    const planCall = fetchMock.mock.calls.find(([url]) => url.endsWith('/factory/plan'))!
    expect(JSON.parse(String(planCall[1]!.body))).toEqual({ action: 'move', options: { type: 'agent', name: 'mine' }, target: 'base' })
    expect(w.get('[data-test="move-repo-plan"]').text()).toContain('.factory/agents/mine/agent.md')
    expect(w.get('[data-test="move-library-plan"]').text()).toContain('agents/mine/agent.md')
    expect(w.emitted('busy')?.at(-1)).toEqual([true])
    await w.get('[data-test="item-move-apply"]').trigger('click'); await flushPromises()
    expect(openDialog()).not.toBeNull()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/apply'))).toBe(false)
    await answerDialog(true)
    const applyCall = fetchMock.mock.calls.find(([url]) => url.endsWith('/factory/apply'))!
    expect(JSON.parse(String(applyCall[1]!.body))).toEqual({ action: 'move', options: { type: 'agent', name: 'mine' }, target: 'base', digest: 'move-digest' })
    expect(w.get('[data-test="item-result"]').text()).toContain('feedbee')
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/factory/items'))).toHaveLength(2)
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/factory/roster'))).toHaveLength(2)
    expect(w.emitted('success')).toHaveLength(1)
    expect(w.find('[data-test="item-move-plan"]').exists()).toBe(false)
  })

  it('shows blockers and does not apply a blocked plan', async () => {
    stub({ ...plan, blockers: [{ code: 'library_dirty', message: 'library has changes' }] })
    const w = mountItems(); await flushPromises()
    await w.get('[data-test="item-move-agent-mine"]').trigger('click'); await flushPromises()
    expect(w.get('[data-test="plan-blocker"]').text()).toContain('library has changes')
    expect(w.get('[data-test="item-move-apply"]').attributes('disabled')).toBeDefined()
  })
})
