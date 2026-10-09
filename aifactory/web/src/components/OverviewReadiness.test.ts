import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import OverviewView from '@/views/OverviewView.vue'
import OverviewReadiness from './OverviewReadiness.vue'
import type { MachineCheck, RepoItem } from '@/lib/api'
import { overview, repo } from '@/test/overviewFixtures'

const registered: RepoItem = { id: 'a', name: 'A', path: '/w/a', added_at: '', status: 'ok', factory: null }
const machine: MachineCheck = { ok: true, findings: [], checked_at: 'now', cached: false, harness_repos: { codex: 1 } }

function envelope(data: unknown) { return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] })) }
function stub(options: { machine?: MachineCheck; repos?: RepoItem[]; fail?: boolean } = {}) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/api/machine/check')) {
      if (options.fail) throw new Error('Server není dostupný')
      return envelope(options.machine ?? machine)
    }
    if (url === '/api/library') return envelope({ exists: true })
    if (url === '/api/repos') return envelope({ repos: options.repos ?? [registered] })
    if (url === '/api/repos/a/factory/roster') return envelope({ agents: [{ name: 'builder' }], workflow_tasks: {} })
    if (url === '/api/repos/a/backlog') return envelope({ items: [{ id: 'M01' }] })
    if (url === '/api/overview') return envelope(overview([repo('a')]))
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

enableAutoUnmount(afterEach)
beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] }))
afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

describe('overview readiness', () => {
  it('keeps a green chip visible and runs a fresh check when clicked', async () => {
    const fetchMock = stub()
    const wrapper = mount(OverviewReadiness, { props: { chip: true } })
    expect(wrapper.get('[data-test="readiness-checking"]').text()).toBe('Probíhá kontrola')
    await flushPromises()
    expect(wrapper.get('[data-test="readiness-success"]').text()).toBe('Systém v pořádku')
    await vi.advanceTimersByTimeAsync(10000)
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
    const before = fetchMock.mock.calls.length
    await wrapper.get('[data-test="readiness-success"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.length).toBeGreaterThan(before)
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1')
    const overviewWrapper = mount(OverviewView, { props: { repos: [registered] } })
    await flushPromises()
    expect(overviewWrapper.get('[data-test="repo-page"]').text()).toContain('Přehled')
    expect(overviewWrapper.find('[data-test="readiness-success"]').exists()).toBe(false)
  })

  it('links the warning chip to problems and provides concrete fixes on that page', async () => {
    const options: { machine: MachineCheck } = { machine: { ...machine, ok: false, findings: [{ code: 'tool_missing', severity: 'error', scope: 'machine', message: 'Chybí Git.', fix: 'Nainstaluj Git.', action: null }] } }
    stub(options)
    const chip = mount(OverviewReadiness, { props: { chip: true } })
    const detail = mount(OverviewReadiness)
    await flushPromises()
    expect(chip.get('[data-test="readiness-warning"]').text()).toBe('Nalezeny problémy')
    expect(chip.get('[data-test="readiness-warning"]').attributes('href')).toBe('#/problems')
    expect(detail.get('[data-test="readiness-warning"] strong').text()).toBe('Chybí Git.')
    expect(detail.get('[data-test="readiness-warning"] li span').text()).toBe('Nainstaluj Git.')
    expect(detail.get('[data-test="readiness-warning"] a').attributes('href')).toBe('#/setup')
    options.machine = machine
    await detail.get('[data-test="readiness-retry"]').trigger('click')
    await flushPromises()
    expect(detail.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it('offers the configuration commit action when a repository has uncommitted configuration', async () => {
    stub({ repos: [{ ...registered, status: 'uncommitted' }] })
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    const warning = wrapper.get('[data-test="readiness-warning"]')
    expect(warning.text()).toContain('A: neuložená konfigurace')
    expect(warning.get('a').attributes('href')).toBe('#/r/a/factory/config_commit')
    expect(warning.text()).not.toContain('První projekt')
  })

  it('offers a retry after a failed request and rechecks on returning to the window', async () => {
    const options = { fail: true }
    stub(options)
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    expect(wrapper.get('[data-test="readiness-warning"]').text()).toContain('Server není dostupný')
    options.fail = false
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(wrapper.find('[data-test="readiness-success"]').exists()).toBe(true)
  })

  it('removes its focus listener on unmount', async () => {
    const fetchMock = stub()
    const wrapper = mount(OverviewReadiness)
    await flushPromises()
    const count = fetchMock.mock.calls.length
    wrapper.unmount()
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(fetchMock.mock.calls).toHaveLength(count)
  })
})
