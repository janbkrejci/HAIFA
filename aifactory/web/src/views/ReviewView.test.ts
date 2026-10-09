import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ReviewView from './ReviewView.vue'
import { APPROVE_NOTE, donePr, reviewDetail, reviewList, reviewPr, taskPr } from '@/test/reviewFixtures'
import { LIVE_DEBOUNCE_MS, resetLiveForTests } from '@/lib/live'
import { FakeEventSource, filesEvent, traceEvent } from '@/test/fakeEventSource'
import { answerDialog } from '@/test/modal'
import { deferred, type Deferred } from '@/test/deferred'

function ok(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

function fail(code: string, message: string, status: number) {
  return new Response(
    JSON.stringify({ ok: false, data: null, error: { code, message, path: null, id: null, issues: [] }, warnings: [] }),
    { status },
  )
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

beforeEach(() => {
  window.localStorage.clear()
})

function debounce() {
  return new Promise((resolve) => setTimeout(resolve, LIVE_DEBOUNCE_MS + 20))
}

afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
  go('#/r/haifa/review')
})

describe('ReviewView', () => {
  it('loads all open PRs once, without an owner filter', async () => {
    go('#/r/haifa/review')
    const fetchMock = vi.fn(async (_url: string) => ok(reviewList()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Review')
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(['/api/repos/haifa/review'])
    expect(wrapper.findAll('tr[data-pr]')).toHaveLength(2)
    expect(wrapper.find('[data-test="owner-filter"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="mine-only"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('neither reads nor writes a stored owner', async () => {
    go('#/r/haifa/review')
    window.localStorage.setItem('factory.review.owner', 'bob')
    const getItem = vi.spyOn(Storage.prototype, 'getItem')
    const setItem = vi.spyOn(Storage.prototype, 'setItem')
    const fetchMock = vi.fn(async (_url: string) => ok(reviewList()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(['/api/repos/haifa/review'])
    expect(getItem).not.toHaveBeenCalledWith('factory.review.owner')
    expect(setItem.mock.calls.some(([key]) => key === 'factory.review.owner')).toBe(false)
    expect(window.localStorage.getItem('factory.review.owner')).toBe('bob')
    wrapper.unmount()
  })

  it('survives a response without prs', async () => {
    go('#/r/haifa/review')
    vi.stubGlobal('fetch', vi.fn(async () => ok({ version: '0.1.0' })))
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(wrapper.find('[data-test="no-prs"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('approves and reloads the detail', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    let merged = false
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        merged = true
        return ok({
          ok: true,
          task_id: 'M01-S01-T01',
          pr: taskPr({ state: 'merged' }),
          merge_sha: 'abcdef1234',
          strategy: 'merge',
          reviewed: false,
          approve_review_sent: false,
          approve_note: APPROVE_NOTE,
        })
      }
      return ok(
        merged
          ? reviewDetail({ provider_state: 'merged', actions: { approve: false, return: false, resolve: false } })
          : reviewDetail(),
      )
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/review/M01-S01-T01')
    const back = wrapper.find('a[data-test="back"]')
    expect(back.find('svg').exists()).toBe(true)
    expect(back.text()).toBe('všechny PR')
    expect(back.attributes('href')).toBe('#/r/haifa/review')
    await wrapper.find('[data-test="approve"]').trigger('click')
    await answerDialog(true)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/review/M01-S01-T01/approve', { method: 'POST' })
    const gets = fetchMock.mock.calls.filter(([u, i]) => u === '/api/repos/haifa/review/M01-S01-T01' && !i)
    expect(gets).toHaveLength(2)
    expect(wrapper.find('[data-test="notice"]').text()).toContain('Sloučeno (merge abcdef1)')
    expect(wrapper.find('[data-test="notice"]').text()).toContain('OB3')
    const box = wrapper.find('[data-test="merged"]')
    expect(box.text()).toContain('pořadí určuje kanban')
    // no other open PR: only the way back to the list
    expect(wrapper.find('[data-test="next-pr"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="back-to-list"]').attributes('href')).toBe('#/r/haifa/review')
    // the merged PR is read only: no approve button any more
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="read-only"]').text()).toContain('sloučeno')
    wrapper.unmount()
  })

  it('offers the next PR waiting for approval after a merge', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return ok({
          ok: true,
          task_id: 'M01-S01-T01',
          pr: taskPr({ state: 'merged' }),
          merge_sha: null,
          strategy: 'merge',
          reviewed: false,
          approve_review_sent: false,
          approve_note: APPROVE_NOTE,
        })
      }
      if (url === '/api/repos/haifa/review') {
        const list = reviewList()
        // the merged PR and one not waiting for review come first: the waiting one wins
        return ok({ ...list, prs: [list.prs[0], list.prs[1], reviewPr({ task_id: 'M04-S01-T01' })] })
      }
      return ok(reviewDetail())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="approve"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.find('[data-test="notice"]').text()).toMatch(/^Sloučeno\./)
    expect(wrapper.find('[data-test="next-pr"]').attributes('href')).toBe('#/r/haifa/review/M04-S01-T01')
    go('#/r/haifa/review/M04-S01-T01')
    await flushPromises()
    expect(wrapper.find('[data-test="merged"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('keeps the return note when the return fails', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail('bad_state', 'PR is not open', 409) : ok(reviewDetail()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="return-note"]').setValue('přidej test')
    await wrapper.find('[data-test="return"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.find('[data-test="error"]').text()).toContain('Vrácení selhalo: PR is not open')
    expect((wrapper.find('[data-test="return-note"]').element as HTMLTextAreaElement).value).toBe('přidej test')
    wrapper.unmount()
  })

  it('returns with a note and links the new run', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return ok(
          { task_id: 'M01-S01-T01', action: 'return', run: { run_id: 'r-new', workflow: 'plan-commit', branch: 'factory/M01-S01-T01-1' }, pending: false },
          202,
        )
      }
      return ok(reviewDetail())
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="return-note"]').setValue('přidej test')
    await wrapper.find('[data-test="return"]').trigger('click')
    await answerDialog(true)
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/review/M01-S01-T01/return')
    expect(post?.[1]?.body).toBe(JSON.stringify({ note: 'přidej test' }))
    expect(wrapper.find('[data-test="started"] a').attributes('href')).toBe('#/r/haifa/runs/r-new')
    // the note was sent: the field is empty again
    expect((wrapper.find('[data-test="return-note"]').element as HTMLTextAreaElement).value).toBe('')
    wrapper.unmount()
  })

  it('resolves a conflict', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        return ok({ task_id: 'M01-S01-T01', action: 'resolve', run: { run_id: 'r-res', workflow: 'resolve', branch: 'b' }, pending: false }, 202)
      }
      return ok(reviewDetail({ mergeability: 'conflict', actions: { approve: false, return: true, resolve: true } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="conflict-banner"] [data-test="resolve"]').trigger('click')
    await flushPromises()
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === 'POST')
    expect(post?.[0]).toBe('/api/repos/haifa/review/M01-S01-T01/resolve')
    expect(wrapper.find('[data-test="started"]').text()).toContain('r-res')
    wrapper.unmount()
  })

  it('shows an API error of an action', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail('conflict', 'PR has a conflict', 409) : ok(reviewDetail()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="approve"]').trigger('click')
    await answerDialog(true)
    const text = wrapper.find('[data-test="error"]').text()
    expect(text).toContain('PR has a conflict')
    expect(text).toContain('použij Vyřešit konflikt s base')
    wrapper.unmount()
  })

  it('says plainly that the trace DB is busy and repeats the action on "Zkusit znovu"', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    let posts = 0
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts += 1
        if (posts === 1) return fail('trace_db_locked', 'sqlite3.OperationalError: database is locked', 503)
        return ok({ task_id: 'M01-S01-T01', action: 'resolve', run: { run_id: 'r-res', workflow: 'resolve', branch: 'b' }, pending: false }, 202)
      }
      return ok(reviewDetail({ mergeability: 'conflict', actions: { approve: false, return: true, resolve: true } }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="conflict-banner"] [data-test="resolve"]').trigger('click')
    await flushPromises()
    const text = wrapper.find('[data-test="error"]').text()
    expect(text).toContain('Databáze běhů je právě obsazená')
    expect(text).not.toContain('database is locked')
    await wrapper.find('[data-test="retry"]').trigger('click')
    await flushPromises()
    expect(posts).toBe(2)
    expect(wrapper.find('[data-test="error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="started"]').text()).toContain('r-res')
    wrapper.unmount()
  })

  it('offers no "Zkusit znovu" for other errors', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail('conflict', 'PR has a conflict', 409) : ok(reviewDetail()),
    ))
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="approve"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.find('[data-test="error"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('reports a task without a PR', async () => {
    go('#/r/haifa/review/M09-S01-T01')
    vi.stubGlobal('fetch', vi.fn(async () => fail('no_pr', 'task M09-S01-T01 has no pull request', 404)))
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(wrapper.find('[data-test="error"]').text()).toContain('nemá PR')
    wrapper.unmount()
  })

  it('refreshes the open PR only for its own task', async () => {
    go('#/r/haifa/review/M01-S01-T01')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async (_url: string) => ok(reviewDetail()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    const detailCalls = () =>
      fetchMock.mock.calls.filter(([url]) => url === '/api/repos/haifa/review/M01-S01-T01').length
    expect(detailCalls()).toBe(1)
    FakeEventSource.latest().emit(
      'trace',
      traceEvent({ runs_changed: true, task_ids: ['M01-S01-T02'] }),
    )
    await debounce()
    await flushPromises()
    expect(detailCalls()).toBe(1)
    FakeEventSource.latest().emit(
      'trace',
      traceEvent({ runs_changed: true, task_ids: ['M01-S01-T01'] }),
    )
    await debounce()
    await flushPromises()
    expect(detailCalls()).toBe(2)
    FakeEventSource.latest().emit(
      'files',
      filesEvent(['backlog/M01-core/S01-model/M01-S01-T01-schema.md']),
    )
    await debounce()
    await flushPromises()
    expect(detailCalls()).toBe(3)
    wrapper.unmount()
  })

  it('refreshes the list quietly when runs change', async () => {
    go('#/r/haifa/review')
    vi.stubGlobal('EventSource', FakeEventSource)
    const fetchMock = vi.fn(async (_url: string) => ok(reviewList()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    FakeEventSource.latest().emit('trace', traceEvent({ run_ids: ['r-1'] }))
    await debounce()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    FakeEventSource.latest().emit('trace', traceEvent({ runs_changed: true, task_ids: ['X'] }))
    await debounce()
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/review')
    wrapper.unmount()
  })

  it('offers "Zobrazit hotové", off by default', async () => {
    go('#/r/haifa/review')
    const fetchMock = vi.fn(async (_url: string) => ok(reviewList()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    const box = wrapper.find<HTMLInputElement>('[data-test="show-done"]')
    expect(box.exists()).toBe(true)
    expect(box.element.checked).toBe(false)
    expect(wrapper.text()).toContain('Zobrazit hotové')
    expect(wrapper.find('[data-test="done"]').exists()).toBe(false)
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(['/api/repos/haifa/review'])
    wrapper.unmount()
  })

  it('loads and shows done PRs when checked and remembers the choice', async () => {
    go('#/r/haifa/review')
    const fetchMock = vi.fn(async (url: string) =>
      ok(url.includes('done=1') ? reviewList({ done: [donePr()] }) : reviewList()),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    await wrapper.find('[data-test="show-done"]').setValue(true)
    await flushPromises()
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(['/api/repos/haifa/review', '/api/repos/haifa/review?done=1'])
    expect(window.localStorage.getItem('haifa.review.showDone')).toBe('1')
    expect(wrapper.find('[data-test="done"]').exists()).toBe(true)
    expect(wrapper.findAll('tr[data-done-pr]').map((r) => r.attributes('data-done-pr'))).toEqual(['M03-S01-T01'])
    await wrapper.find('[data-test="show-done"]').setValue(false)
    await flushPromises()
    expect(window.localStorage.getItem('haifa.review.showDone')).toBe('0')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/review')
    expect(wrapper.find('[data-test="done"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('starts with the remembered choice', async () => {
    go('#/r/haifa/review')
    window.localStorage.setItem('haifa.review.showDone', '1')
    const fetchMock = vi.fn(async (_url: string) => ok(reviewList({ done: [donePr()] })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(fetchMock.mock.calls.map(([u]) => u)).toEqual(['/api/repos/haifa/review?done=1'])
    expect(wrapper.find<HTMLInputElement>('[data-test="show-done"]').element.checked).toBe(true)
    expect(wrapper.findAll('tr[data-done-pr]')).toHaveLength(1)
    wrapper.unmount()
  })

  it('has no "Zobrazit hotové" on the detail, which is read only for a merged PR', async () => {
    go('#/r/haifa/review/M03-S01-T01')
    const merged = donePr()
    const fetchMock = vi.fn(async (_url: string) =>
      ok(
        reviewDetail({
          task_id: merged.task_id,
          provider_state: 'merged',
          awaiting_review: false,
          pr: merged.pr,
          actions: { approve: false, return: false, resolve: false },
        }),
      ),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView)
    await flushPromises()
    expect(wrapper.find('[data-test="show-done"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="read-only"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(false)
    wrapper.unmount()
  })
  describe('switching the open PR', () => {
    const A = 'M01-S01-T01'
    const B = 'M01-S01-T02'

    function slowFetch() {
      const pending: Record<string, Deferred<Response>[]> = {}
      const fetchMock = vi.fn((url: string) => {
        const d = deferred<Response>()
        ;(pending[url] ??= []).push(d)
        return d.promise
      })
      vi.stubGlobal('fetch', fetchMock)
      const answer = (id: string, index = 0) =>
        pending[`/api/repos/haifa/review/${id}`][index].resolve(ok(reviewDetail({ task_id: id, task_title: `Title ${id}` })))
      return { pending, fetchMock, answer }
    }

    it('hides the previous PR at once and shows the new id loading', async () => {
      go(`#/r/haifa/review/${A}`)
      const api = slowFetch()
      const wrapper = mount(ReviewView)
      api.answer(A)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(A)

      go(`#/r/haifa/review/${B}`)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain(`Title ${A}`)
      expect(wrapper.find('[data-test="loading-id"]').text()).toBe(B)

      api.answer(B)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(B)
      expect(wrapper.find('[data-test="detail-loading"]').exists()).toBe(false)
      wrapper.unmount()
    })

    it('does not let a slow older answer overwrite the newer one', async () => {
      go(`#/r/haifa/review/${A}`)
      const api = slowFetch()
      const wrapper = mount(ReviewView)
      await flushPromises()
      go(`#/r/haifa/review/${B}`)
      await flushPromises()
      api.answer(B)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(B)
      api.answer(A)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(B)
      expect(wrapper.text()).not.toContain(`Title ${A}`)
      expect(wrapper.find('[data-test="refresh"]').attributes('disabled')).toBeUndefined()
      wrapper.unmount()
    })

    it('keeps the PR shown while the same PR reloads', async () => {
      go(`#/r/haifa/review/${A}`)
      const api = slowFetch()
      const wrapper = mount(ReviewView)
      api.answer(A)
      await flushPromises()
      await wrapper.find('[data-test="refresh"]').trigger('click')
      await flushPromises()
      expect(api.pending[`/api/repos/haifa/review/${A}`]).toHaveLength(2)
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(A)
      expect(wrapper.find('[data-test="detail-loading"]').exists()).toBe(false)
      api.answer(A, 1)
      await flushPromises()
      expect(wrapper.find('[data-test="task-label"]').text()).toContain(A)
      wrapper.unmount()
    })
  })
})
