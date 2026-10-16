import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoItems from './RepoItems.vue'

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

function stub(library: { library: string | null; library_name?: string | null } = { library: SHA, library_name: 'team' }) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === '/api/repos/a/factory/items') return ok({ ...library, items })
    if (url === '/api/repos/a/factory/roster') return ok(roster)
    if (url === '/api/machine/check') return ok({ findings: [] })
    throw new Error(`unexpected ${url} ${init?.method}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const mountItems = (props: Record<string, unknown> = {}) => mount(RepoItems, { props: { repoId: 'a', ...props }, attachTo: document.body })

describe('RepoItems', () => {
  it('is Nastavení agentů with every agent once and nothing else of the library', async () => {
    stub()
    const w = mountItems(); await flushPromises()
    expect(w.get('h2').text()).toBe('Nastavení agentů')
    expect(w.findAll('[data-test="roster-agent-builder"]')).toHaveLength(1)
    expect(w.findAll('[data-test="roster-agent-mine"]')).toHaveLength(1)
    expect(w.get('[data-test="roster-agent-builder"]').text()).toContain('z knihovny')
    expect(w.get('[data-test="roster-agent-mine"]').text()).toContain('vlastní kopie')
    // workflows, skills and extensions and the move are on the Knihovna page
    expect(w.find('[data-test^="items-"]:not([data-test="items-inherit"])').exists()).toBe(false)
    expect(w.find('[data-test="item-skill-lint"]').exists()).toBe(false)
    expect(w.find('[data-test="item-workflow-mine-flow"]').exists()).toBe(false)
    expect(w.find('[data-test^="item-move"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Přesunout do knihovny')
    expect(w.text()).not.toContain('Vybavení továrny')
  })

  it('names the library and its short commit, with a space and no full SHA', async () => {
    stub()
    const w = mountItems(); await flushPromises()
    const hint = w.get('[data-test="items-inherit"]').text()
    expect(hint).toBe('Agent bez vlastní kopie v .factory/ se dědí z knihovny „team“ (aa8e980).')
    expect(w.text()).not.toContain(SHA)
  })

  it('names the built-in set without a library', async () => {
    stub({ library: null })
    const w = mountItems(); await flushPromises()
    expect(w.get('[data-test="items-inherit"]').text()).toContain('vestavěné výchozí sady')
  })

  it('collapses by its heading and reloads the library and the roster', async () => {
    const fetchMock = stub()
    const w = mountItems(); await flushPromises()
    const toggle = w.get('[data-test="section-toggle"]')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(w.get('[data-test="roster-editor"]').isVisible()).toBe(false)
    expect(w.emitted('update:open')).toEqual([[false]])
    await toggle.trigger('click')
    expect(w.get('[data-test="roster-editor"]').isVisible()).toBe(true)
    await (w.vm as unknown as { reload: () => Promise<void> }).reload(); await flushPromises()
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/factory/items'))).toHaveLength(2)
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/factory/roster'))).toHaveLength(2)
  })
})
