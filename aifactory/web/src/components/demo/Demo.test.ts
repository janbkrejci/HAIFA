import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { DEMO_REPO, lastStart } from '@/lib/demo'
import { answerDialog, openDialog } from '@/test/modal'
import DemoBanner from './DemoBanner.vue'
import DemoSteps from './DemoSteps.vue'
import RemoveDemoButton from './RemoveDemoButton.vue'
import TryDemoButton from './TryDemoButton.vue'
import type { RunSummary } from '@/lib/runs'

enableAutoUnmount(afterEach)

function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

afterEach(() => {
  vi.unstubAllGlobals()
  lastStart.value = null
})

function summary(over: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: 'r1', task_id: 'DEMO-S01-T01', task_title: 'Počet znaků', workflow: 'build-test', state: 'running',
    branch: 'task/DEMO-S01-T01', started_at: '2026-10-17T10:00:00+00:00', ended_at: null, duration_s: null,
    tokens: 0, cost: 0, error: null, note: null, pr: null, phases: [], ...over,
  }
}

describe('TryDemoButton', () => {
  it('creates the sample, starts its first task and opens the backlog on it', async () => {
    const fetchMock = vi.fn(async (url: string) => {
      if (url === '/api/demo') return envelope({ path: '/h/demo', created: true, registered: true, repo_id: 'demo', base: 'main', provider: 'local' })
      if (url === '/api/machine/harnesses') return envelope({ settings: { version: 1, default_harness: 'claude', harnesses: { claude: { enabled: true, model: 'm' } } }, available: { claude: true }, models: {}, configured: true, tests: { claude: { m: { ok: true } } } })
      if (url.endsWith('/run')) return envelope({ run: { run_id: 'r1' }, pending: false })
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const applied = vi.fn()
    window.addEventListener('factory-applied', applied)
    const wrapper = mount(TryDemoButton)

    await wrapper.get('[data-test=try-demo]').trigger('click')
    await flushPromises()

    expect(window.location.hash).toBe('#/r/demo/backlog/DEMO-S01-T01')
    expect(wrapper.emitted('started')).toEqual([['demo']])
    expect(applied).toHaveBeenCalled()
    expect(lastStart.value?.runId).toBe('r1')
    window.removeEventListener('factory-applied', applied)
  })

  it('shows why the sample could not be made and stays', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: false, data: null, error: { code: 'git_identity_missing', message: 'git has no identity' }, warnings: [] }), { status: 409 })))
    const before = window.location.hash
    const wrapper = mount(TryDemoButton)

    await wrapper.get('[data-test=try-demo]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-test=try-demo-error]').text()).toContain('git has no identity')
    expect(window.location.hash).toBe(before)
  })
})

describe('RemoveDemoButton', () => {
  it('asks, deletes the sample with its folder and goes to the overview', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => envelope({ path: '/h/demo', repo_id: 'demo', deleted: true }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RemoveDemoButton, { props: { path: '/h/demo' }, attachTo: document.body })

    await wrapper.get('[data-test=remove-demo]').trigger('click')
    expect(openDialog()?.textContent).toContain('/h/demo')
    await answerDialog(true)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0]?.[0]).toBe('/api/demo')
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe('DELETE')
    expect(window.location.hash).toBe('#/overview')
  })

  it('does nothing when cancelled', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(RemoveDemoButton, { attachTo: document.body })

    await wrapper.get('[data-test=remove-demo]').trigger('click')
    await answerDialog(false)

    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('DemoBanner', () => {
  it('links the run the last start began and offers an own repo', () => {
    lastStart.value = { repoId: 'demo', harness: { harness: 'claude', model: 'm' }, runId: 'r1', error: null }
    window.location.hash = '#/r/demo/backlog'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    const wrapper = mount(DemoBanner, { props: { repoId: 'demo' } })

    expect(wrapper.get('[data-test=demo-started]').text()).toContain('claude (m)')
    expect(wrapper.get('[data-test=demo-run-link]').attributes('href')).toBe('#/r/demo/runs/r1')
    expect(wrapper.get('[data-test=demo-add-repo]').attributes('href')).toBe('#/repos/add')
  })

  it('reports a run that did not start', () => {
    lastStart.value = { repoId: 'demo', harness: null, runId: null, error: 'no harness' }
    const wrapper = mount(DemoBanner, { props: { repoId: 'demo' } })

    expect(wrapper.get('[data-test=demo-start-error]').text()).toContain('no harness')
    expect(wrapper.find('[data-test=demo-started]').exists()).toBe(false)
  })
})

describe('DemoSteps', () => {
  it('explains the current step while the run goes on', () => {
    const wrapper = mount(DemoSteps, { props: { run: summary(), phases: [{ seq: 1, name: 'build', status: 'running' }] } })

    expect(wrapper.get('[data-step=worktree]').attributes('data-state')).toBe('done')
    expect(wrapper.get('[data-step=build]').attributes('data-state')).toBe('current')
    expect(wrapper.get('[data-step=build]').text()).toContain('builder')
    expect(wrapper.find('[data-test=demo-finished]').exists()).toBe(false)
  })

  it('sends to Review while the PR waits, and offers an own repo after the merge', async () => {
    const pr = { url: '', pr_id: '1', state: 'open' }
    const wrapper = mount(DemoSteps, {
      props: { run: summary({ state: 'succeeded', pr }), phases: [] },
      global: { provide: { [DEMO_REPO as symbol]: ref('/h/demo') } },
      attachTo: document.body,
    })
    expect(wrapper.get('[data-test=demo-review-link]').attributes('href')).toContain('/review/DEMO-S01-T01')

    await wrapper.setProps({ run: summary({ state: 'succeeded', pr: { ...pr, state: 'merged' } }) })

    expect(wrapper.find('[data-test=demo-review-hint]').exists()).toBe(false)
    expect(wrapper.get('[data-test=demo-finished]').text()).toContain('celým cyklem')
    expect(wrapper.get('[data-test=demo-finished-add-repo]').attributes('href')).toBe('#/repos/add')
    await wrapper.get('[data-test=remove-demo]').trigger('click')
    expect(openDialog()?.textContent).toContain('/h/demo')
    await answerDialog(false)
  })
})
