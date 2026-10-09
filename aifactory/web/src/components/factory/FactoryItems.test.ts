import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { chooseOption, selectLabels } from '@/test/select'
import FactoryItems from './FactoryItems.vue'
import { ApiError, factoryItemChoices, type FactoryItemRequest, type FactoryRepoItem, type FactoryRosterAgent } from '@/lib/api'
const api = vi.hoisted(() => ({ items: vi.fn(), roster: vi.fn(), library: vi.fn(), repos: vi.fn(), preview: vi.fn(), apply: vi.fn(), diff: vi.fn() }))
vi.mock('@/lib/api', async original => ({ ...await original<object>(), fetchFactoryItems: api.items, fetchFactoryRoster: api.roster, fetchRepos: api.repos, previewFactoryItem: api.preview, applyFactoryItem: api.apply, fetchFactoryItemDiff: api.diff }))
vi.mock('@/lib/library', async original => ({ ...await original<object>(), fetchLibrary: api.library }))
enableAutoUnmount(afterEach)
afterEach(() => { vi.clearAllMocks(); document.body.innerHTML = '' })
const row = (state: FactoryRepoItem['state'] = 'synced', type: FactoryRepoItem['type'] = 'agent', name = 'builder'): FactoryRepoItem => ({ type, name, item: name, state, repo_version: 'r', manifest_version: 'm', library_version: 'l' })
function setup(rows = [row()], bindings: Partial<FactoryRosterAgent> = {}) {
  api.items.mockResolvedValue({ items: rows })
  api.roster.mockImplementation(async id => ({ agents: [{ name: id === 'b' ? 'reviewer' : 'builder', purpose: 'Build code', harness: 'claude', model: 'sonnet', thinking: 'high', skills: ['lint'], extensions: ['tools'], writes: ['src/'], ...bindings }], workflow_tasks: { flow: 3 } }))
  api.library.mockResolvedValue({ exists: true, items: [{ type: 'skill', name: 'lint' }, { type: 'agent', name: 'builder' }] })
  api.repos.mockResolvedValue({ repos: [{ id: 'a', name: 'A', status: 'ok' }, { id: 'b', name: 'B', status: 'ok' }] })
  api.preview.mockResolvedValue({ digest: 'reviewed', files: [], blockers: [], added: [{ type: 'skill', name: 'lint' }] })
  api.apply.mockResolvedValue({ commit: 'abc' })
  api.diff.mockResolvedValue({ manifest: { available: true, files: [] }, head: { available: false, reason: 'unknown' } })
  return mount(FactoryItems, { props: { repoId: 'a' }, attachTo: document.body })
}
async function review(w: ReturnType<typeof setup>) { await w.get('form').trigger('submit'); await flushPromises() }
async function execute(w: ReturnType<typeof setup>) {
  await w.get('[data-test="item-apply"]').trigger('click'); await flushPromises()
  document.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')!.click(); await flushPromises()
}
describe('Factory items', () => {
  it('renders server states, roster ownership and workflow counts', async () => {
    const states = ['local', 'missing', 'synced', 'unknown', 'outdated', 'modified', 'diverged'] as const
    const w = setup([...states.map(s => row(s, 'skill', s)), row(), row('synced', 'workflow', 'flow')]); await flushPromises()
    expect(w.findAll('[data-state]').map(e => e.attributes('data-state'))).toEqual(expect.arrayContaining([...states]))
    expect(w.get('[data-test="items-agent"]').text()).toContain('Purpose · vlastní knihovna')
    expect(w.get('[data-test="item-agent-builder"]').text()).toContain('Build code')
    expect(w.get('[data-test="item-workflow-flow"]').text()).toContain('3')
  })
  it('leaves agent bindings to the roster editor: no inline set action', async () => {
    const w = setup(); await flushPromises()
    const actions = w.get('[data-test="item-agent-builder"] .row-actions').findAll('button').map(b => b.text())
    expect(actions).not.toContain('Nastavit')
    expect(w.get('[data-test="item-agent-builder"]').text()).toContain('sonnet')
  })
  it('refuses preview when required dropdown choices are missing', async () => {
    const w = setup(); await flushPromises(); await w.get('[data-test="item-add"]').trigger('click')
    expect(w.get('[data-test="item-preview"]').attributes('disabled')).toBeDefined()
    await review(w); expect(api.preview).not.toHaveBeenCalled()
    await w.get('[data-test="item-close"]').trigger('click')
    await w.get('[data-test="item-copy"]').trigger('click')
    await review(w); expect(api.preview).not.toHaveBeenCalled()
  })
  it('adds a skill with agent binding and dependency closure', async () => {
    const w = setup(); await flushPromises(); await w.get('[data-test="item-add"]').trigger('click')
    await chooseOption(w, '[data-test="item-type"]', 'skill'); await chooseOption(w, '[data-test="item-name"]', 'lint'); await chooseOption(w, '[data-test="item-agent"]', 'builder')
    await review(w); expect(w.text()).toContain('skill/lint'); expect(api.apply).not.toHaveBeenCalled(); await execute(w)
    expect(api.apply).toHaveBeenCalledWith({ action: 'add', options: { type: 'skill', name: 'lint', agent: 'builder' }, target: 'base' }, 'reviewed', '', 'a')
  })
  it.each(['update', 'export', 'revert', 'remove'] as const)('reviews and confirms %s', async action => {
    const w = setup(); await flushPromises(); await w.get(`[data-test="item-${action}"]`).trigger('click')
    if (action === 'export') await w.get('[data-test="item-slot"]').setValue('custom')
    if (action === 'revert') await chooseOption(w, '[data-test="item-revert-to"]', 'head')
    await review(w); expect(api.apply).not.toHaveBeenCalled(); await execute(w)
    const body = api.apply.mock.calls[0][0] as FactoryItemRequest
    expect(body.action).toBe(action)
    expect(body.options).toEqual(action === 'update' ? { item: ['agent/builder'] } : { type: 'agent', name: 'builder', ...(action === 'export' ? { slot: 'custom' } : {}), ...(action === 'revert' ? { to: 'head' } : {}) })
  })
  it('loads read-only diff', async () => {
    const w = setup(); await flushPromises(); await w.get('[data-test="item-diff"]').trigger('click'); await flushPromises()
    expect(w.text()).toContain('Proti manifest'); expect(w.text()).toContain('unknown'); expect(api.apply).not.toHaveBeenCalled()
  })
  it.each(['slot_taken', 'in_use', 'library_changed_since', 'run_in_progress'])('blocks %s with a repair', async code => {
    const w = setup(); await flushPromises(); api.preview.mockRejectedValueOnce(new ApiError(code, 'blocked'))
    await w.get('[data-test="item-remove"]').trigger('click'); await review(w)
    expect(w.get('[data-test="item-apply"]').attributes('disabled')).toBeDefined(); expect(w.get('[role="alert"]').text()).toContain('Oprava:'); expect(api.apply).not.toHaveBeenCalled()
  })
  it('blocks returned plan blockers', async () => {
    const w = setup(); await flushPromises(); api.preview.mockResolvedValueOnce({ digest: 'blocked', files: [], blockers: [{ code: 'in_use', message: 'Used' }] })
    await w.get('[data-test="item-remove"]').trigger('click'); await review(w)
    expect(w.get('[data-test="item-apply"]').attributes('disabled')).toBeDefined()
  })
  it('copies a modified item through two separate confirmations', async () => {
    const w = setup([row('modified')]); await flushPromises(); await w.get('[data-test="item-copy"]').trigger('click'); await chooseOption(w, '[data-test="item-destination"]', 'b'); await flushPromises()
    await review(w); expect(api.preview.mock.calls[0][0].action).toBe('export'); await execute(w)
    expect(api.apply).toHaveBeenCalledTimes(1); expect(w.text()).toContain('2. Přidání')
    expect(w.get('[data-test="item-apply"]').attributes('disabled')).toBeDefined()
    await w.get('[data-test="item-slot"]').setValue('extra'); await review(w)
    expect(api.preview).toHaveBeenLastCalledWith(expect.objectContaining({ action: 'add', options: expect.objectContaining({ name: 'builder', slot: 'extra' }) }), 'b')
    await execute(w); expect(api.apply).toHaveBeenCalledTimes(2); expect(api.apply.mock.calls[1][3]).toBe('b')
  })
  it('copies synced skills directly using destination bindings', async () => {
    const w = setup([row('synced', 'skill', 'lint')]); await flushPromises(); await w.get('[data-test="item-copy"]').trigger('click'); await chooseOption(w, '[data-test="item-destination"]', 'b'); await flushPromises()
    expect(await selectLabels(w, '[data-test="item-agent"]')).toEqual(['Bez vazby', 'reviewer'])
    await chooseOption(w, '[data-test="item-agent"]', 'reviewer'); await review(w); await execute(w)
    expect(api.apply).toHaveBeenCalledWith(expect.objectContaining({ action: 'add', options: { type: 'skill', name: 'lint', agent: 'reviewer' } }), 'reviewed', '', 'b')
  })
  it('replans conflict takeover choices before allowing apply', async () => {
    const w = setup(); await flushPromises()
    api.preview.mockResolvedValueOnce({ digest: 'conflict', files: [], blockers: [{ code: 'conflict', message: 'Changed in both' }], update: { items: [{ type: 'agent', name: 'builder', action: 'conflict', merge_available: true, files: [{ file: 'system.md', status: 'conflict', diff: null, ours_diff: '+ours', theirs_diff: '+theirs' }] }], migrations: [] } })
    await w.get('[data-test="item-update"]').trigger('click'); await review(w)
    expect(w.get('[data-test="item-apply"]').attributes('disabled')).toBeDefined()
    await w.get('input[type="checkbox"]').setValue(true); await flushPromises()
    expect(api.preview).toHaveBeenLastCalledWith(expect.objectContaining({ options: { item: ['agent/builder'], take: ['agent/builder:system.md'] } }), 'a')
    expect(api.apply).not.toHaveBeenCalled()
  })
  it('does not advance a failed export or reuse a stale digest', async () => {
    const w = setup([row('modified')]); await flushPromises(); await w.get('[data-test="item-copy"]').trigger('click'); await chooseOption(w, '[data-test="item-destination"]', 'b'); await flushPromises()
    api.apply.mockRejectedValueOnce(new ApiError('plan_changed', 'Review again'))
    await review(w); await execute(w)
    expect(w.text()).toContain('1. Export')
    expect(w.get('[data-test="item-apply"]').attributes('disabled')).toBeDefined()
    await review(w); expect(api.preview.mock.calls.at(-1)![0].action).toBe('export')
  })
  it('filters injected paths and file contents', () => {
    expect(factoryItemChoices('add', { type: 'agent', name: 'builder', path: '/tmp', content: 'secret', files: [] } as never)).toEqual({ type: 'agent', name: 'builder' })
  })
})
