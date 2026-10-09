import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import GettingStarted from './GettingStarted.vue'
import type { RepoItem } from '@/lib/api'

function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

const REPO: RepoItem = { id: 'a', name: 'A', path: '/w/a', added_at: '', status: 'ok', factory: null }

function stub(projects: unknown[]) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url.startsWith('/api/machine/check')) return envelope({ ok: true, findings: [], checked_at: 'now', cached: false, harness_repos: { claude: 1 } })
    if (url === '/api/library') return envelope({ exists: true })
    if (url === '/api/repos/a/factory/roster') return envelope({ agents: [{ name: 'builder' }], workflow_tasks: {} })
    if (url === '/api/repos/a/backlog') return envelope({ items: projects })
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())

describe('GettingStarted', () => {
  it('highlights the next step with its link and folds away', async () => {
    stub([])
    const w = mount(GettingStarted, { props: { repos: [REPO] } })
    await flushPromises()
    const steps = w.findAll('[data-test="getting-started-step"]')
    expect(steps).toHaveLength(7)
    expect(steps.filter((s) => s.attributes('data-done') === 'true')).toHaveLength(6)
    expect(w.get('[data-test="getting-started-next"]').attributes('href')).toBe('#/r/a/backlog/new-container')
    await w.get('[data-test="getting-started-toggle"]').trigger('click')
    expect(w.find('[data-test="getting-started-step"]').exists()).toBe(false)
  })

  it('is hidden when all is ready', async () => {
    stub([{ id: 'M01' }])
    const w = mount(GettingStarted, { props: { repos: [REPO] } })
    await flushPromises()
    expect(w.find('[data-test="getting-started"]').exists()).toBe(false)
  })

  it('uses the check and library it is given and reads no repo of none', async () => {
    const fetchMock = stub([])
    const w = mount(GettingStarted, { props: { repos: [], check: null, library: null } })
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
    expect(w.get('[data-test="getting-started-next"]').attributes('href')).toBe('#/setup')
  })
})
