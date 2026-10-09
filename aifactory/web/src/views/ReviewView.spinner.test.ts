// Spinners on review actions: the clicked button spins until the server answers,
// and a `pending` run keeps spinning until it shows up in live updates.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ReviewView from './ReviewView.vue'
import { APPROVE_NOTE, reviewDetail, reviewList, taskPr } from '@/test/reviewFixtures'
import { deferred } from '@/test/deferred'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, traceEvent } from '@/test/fakeEventSource'
import { answerDialog } from '@/test/modal'

const TASK = 'M01-S01-T01'

function ok(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function debounce() {
  return new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
}

function spins(wrapper: VueWrapper, test: string): boolean {
  return wrapper.find(`[data-test="${test}"] [data-test="spinner"]`).exists()
}

function disabled(wrapper: VueWrapper, test: string): boolean {
  return wrapper.find(`[data-test="${test}"]`).attributes('disabled') !== undefined
}

const approved = () =>
  ok({
    ok: true,
    task_id: TASK,
    pr: taskPr({ state: 'merged' }),
    merge_sha: 'abcdef1234',
    strategy: 'merge',
    reviewed: false,
    approve_review_sent: false,
    approve_note: APPROVE_NOTE,
  })

const started = (action: 'return' | 'resolve', runId: string | null) =>
  ok(
    {
      task_id: TASK,
      action,
      run: runId ? { run_id: runId, workflow: 'plan-commit', branch: 'factory/M01-S01-T01-1' } : null,
      pending: runId === null,
    },
    202,
  )

const newRun = {
  run_id: 'r-new',
  workflow: 'plan-commit',
  state: 'running',
  started_at: '2026-01-02T10:00:00+00:00',
  ended_at: null,
  note: null,
  error: null,
  cost: 0,
  tokens: 0,
}

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/review')
})

describe('ReviewView spinners', () => {
  // Schválit, Vrátit, Vyřešit konflikt
  it.each(['approve', 'return', 'resolve'] as const)('spins only %s until the server answers', async (action) => {
    go(`#/r/haifa/review/${TASK}`)
    const gate = deferred<Response>()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (_url: string, init?: RequestInit) => {
        if (init?.method === 'POST') return gate.promise
        return ok(reviewDetail({ mergeability: 'conflict' }))
      }),
    )
    const wrapper = mount(ReviewView)
    await flushPromises()
    if (action === 'return') await wrapper.find('[data-test="return-note"]').setValue('přidej test')
    await wrapper.find(`[data-test="${action}"]`).trigger('click')
    if (action !== 'resolve') await answerDialog(true)
    await flushPromises()
    expect(spins(wrapper, action)).toBe(true)
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(1)
    for (const other of ['approve', 'return', 'resolve']) expect(disabled(wrapper, other)).toBe(true)
    gate.resolve(action === 'approve' ? approved() : started(action, 'r-new'))
    await flushPromises()
    expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it.each(['return', 'resolve'] as const)(
    'keeps spinning a pending %s until the run shows up in live updates',
    async (action) => {
      go(`#/r/haifa/review/${TASK}`)
      vi.stubGlobal('EventSource', FakeEventSource)
      let launched = false
      vi.stubGlobal(
        'fetch',
        vi.fn(async (_url: string, init?: RequestInit) => {
          if (init?.method === 'POST') return started(action, null)
          const base = reviewDetail({ mergeability: 'conflict' })
          return ok(launched ? { ...base, runs: [...base.runs, newRun] } : base)
        }),
      )
      const wrapper = mount(ReviewView)
      await flushPromises()
      if (action === 'return') await wrapper.find('[data-test="return-note"]').setValue('přidej test')
      await wrapper.find(`[data-test="${action}"]`).trigger('click')
      if (action === 'return') await answerDialog(true)
      await flushPromises()
      expect(spins(wrapper, action)).toBe(true)
      expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(1)
      for (const other of ['approve', 'return', 'resolve']) expect(disabled(wrapper, other)).toBe(true)
      expect(wrapper.find('[data-test="started"]').text()).toContain('Běh se spouští')
      expect(wrapper.find('[data-test="started"] a').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('obnov stránku')

      launched = true
      FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: [TASK] }))
      await debounce()
      await flushPromises()
      expect(wrapper.findAll('[data-test="spinner"]')).toHaveLength(0)
      expect(wrapper.find('[data-test="started"] a').text()).toBe('r-new')
      expect(wrapper.find('[data-test="started"] a').attributes('href')).toBe('#/r/haifa/runs/r-new')
      expect(wrapper.text()).not.toContain('obnov stránku')
      wrapper.unmount()
    },
  )

  it('spins the refresh icon and shows no empty list before the first load', async () => {
    go('#/r/haifa/review')
    const list = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(async () => list.promise))
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).toContain('spin')
    expect(wrapper.find('[data-test="no-prs"]').exists()).toBe(false)
    list.resolve(ok(reviewList({ prs: [] })))
    await flushPromises()
    expect(wrapper.find('[data-test="refresh"] svg').classes()).not.toContain('spin')
    expect(wrapper.find('[data-test="no-prs"]').exists()).toBe(true)
    wrapper.unmount()
  })
})
