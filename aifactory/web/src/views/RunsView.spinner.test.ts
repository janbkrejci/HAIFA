import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunsView from './RunsView.vue'
import { detail, events, runsResponse } from '@/test/runsFixtures'
import { deferred } from '@/test/deferred'
import { resetLiveForTests } from '@/lib/live'
import { FakeEventSource } from '@/test/fakeEventSource'
import { answerDialog } from '@/test/modal'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/runs')
})

describe('RunsView spinners', () => {
  it('spins Zastavit until the stop answers', async () => {
    go('#/r/haifa/runs/r-run')
    const stop = deferred<Response>()
    let state = 'running'
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST') return stop.promise
        if (url.includes('/events')) return ok({ events: events(), cursor: 3, has_more: false })
        return ok(detail({ run_id: 'r-run', state: state as 'running' }))
      }),
    )
    const wrapper = mount(RunsView)
    await flushPromises()
    await wrapper.find('[data-test="stop-run"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.find('[data-test="stop-run"] [data-test="spinner"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(1)
    expect(wrapper.find('[data-test="stop-run"]').attributes('disabled')).toBeDefined()
    state = 'stopped'
    stop.resolve(ok({ run: detail({ run_id: 'r-run', state: 'stopped' }).run, signalled: [1], killed: [] }))
    await flushPromises()
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('spins the refresh icon and shows no empty list before the first load', async () => {
    go('#/r/haifa/runs')
    const list = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => (url === '/api/repos/haifa/chains' ? ok({ chains: [] }) : list.promise)),
    )
    const wrapper = mount(RunsView)
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).toContain('spin')
    expect(wrapper.find('[data-test="no-runs"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="list-loading"]').exists()).toBe(true)
    list.resolve(ok({ ...runsResponse(), runs: [] }))
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).not.toContain('spin')
    expect(wrapper.find('[data-test="no-runs"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
