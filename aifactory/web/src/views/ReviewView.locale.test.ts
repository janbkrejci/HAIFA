import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import { resetLiveForTests } from '@/lib/live'
import { FakeEventSource } from '@/test/fakeEventSource'
import { deferred } from '@/test/deferred'
import { answerDialog, openDialog } from '@/test/modal'
import { donePr, reviewDetail, reviewList } from '@/test/reviewFixtures'
import ReviewView from './ReviewView.vue'
import ReviewList from '@/components/review/ReviewList.vue'
import ReviewDetail from '@/components/review/ReviewDetail.vue'

const ok = (data: unknown) => new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
const fail = (code: string) => new Response(JSON.stringify({
  ok: false, data: null, error: { code, message: 'Původní backendovou větu nepřekládat parsováním.' },
}))
function go(id = '') {
  window.location.hash = `#/r/haifa/review${id ? '/' + id : ''}`
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

enableAutoUnmount(afterEach)
beforeEach(() => {
  localStorage.clear()
  setLocale('en')
  vi.stubGlobal('EventSource', FakeEventSource)
})
afterEach(() => {
  resetLiveForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
  setLocale('en')
})

it('translates the list, done states, loading and empty states in both languages', async () => {
  const list = mount(ReviewList, { props: { list: reviewList({ done: [donePr()] }), showDone: true } })
  expect(list.get('[data-test="awaiting"] h2').text()).toContain('Awaiting review')
  expect(list.get('[data-col="state"]').text()).toBe('merged')
  expect(list.get('[data-test="mergeability"]').text()).toBe('mergeable')
  setLocale('cs')
  await flushPromises()
  expect(list.get('[data-test="awaiting"] h2').text()).toContain('Čeká na review')
  expect(list.get('[data-col="state"]').text()).toBe('sloučeno')
  await list.setProps({ ready: false, loading: true })
  expect(list.get('[data-test="list-loading"]').text()).toBe('Načítám…')
  setLocale('en')
  await flushPromises()
  expect(list.get('[data-test="list-loading"]').text()).toBe('Loading…')
  await list.setProps({ ready: true, list: reviewList({ prs: [] }) })
  expect(list.get('[data-test="no-prs"]').text()).toContain('No PRs to approve.')
  setLocale('cs')
  await flushPromises()
  expect(list.get('[data-test="no-prs"]').text()).toContain('Žádné PR ke schválení.')
})

it('keeps a draft, expanded content and confirmation while switching languages', async () => {
  go('M01-S01-T01')
  const data = reviewDetail()
  const fetchMock = vi.fn(async () => ok(data))
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ReviewView, { attachTo: document.body })
  await flushPromises()
  const note = wrapper.get('[data-test="return-note"]')
  await note.setValue('Přidej český test – preserve this draft')
  for (const section of wrapper.findAll('button.dsec-head')) await section.trigger('click')
  await wrapper.get('[data-test="diff-file-section"] button.dsec-head').trigger('click')
  const body = wrapper.get('[data-test="pr-body"]').element
  const patch = wrapper.get('[data-test="diff-file"] .patch').text()
  expect(wrapper.text()).toContain('Reviewer verdict')
  expect(wrapper.get('[data-test="verdict-state"]').text()).toBe('not approved')
  expect(wrapper.get('[data-test="check"]').text()).toContain('artifacts_exist')
  await wrapper.get('[data-test="return"]').trigger('click')
  await flushPromises()
  expect(openDialog()?.textContent).toContain('Return PR M01-S01-T01 to the agent')
  const requests = fetchMock.mock.calls.length
  setLocale('cs')
  await flushPromises()
  expect(openDialog()?.textContent).toContain('Vrátit PR M01-S01-T01 agentovi')
  expect(openDialog()?.textContent).toContain('Přidej český test – preserve this draft')
  expect(wrapper.get('[data-test="return-note"]').element).toBe(note.element)
  expect(note.element).toHaveProperty('value', 'Přidej český test – preserve this draft')
  expect(wrapper.get('[data-test="pr-body"]').element).toBe(body)
  expect(wrapper.get('[data-test="pr-body"]').text()).toContain('Napiš schema.')
  expect(wrapper.get('[data-test="verdict-state"]').text()).toBe('neschváleno')
  expect(wrapper.text()).toContain('Chybí test.')
  expect(wrapper.text()).toContain('Loader čte YAML')
  expect(wrapper.get('[data-test="diff-file"] .patch').text()).toBe(patch)
  expect(fetchMock.mock.calls.length).toBe(requests)
  setLocale('en')
  await flushPromises()
  expect(openDialog()?.textContent).toContain('Return PR')
  await answerDialog(false)
  await wrapper.get('[data-test="approve"]').trigger('click')
  await flushPromises()
  expect(openDialog()?.textContent).toContain('Approve and merge PR M01-S01-T01 into main?')
  expect(openDialog()?.textContent).toContain('Approval does not yet send an approve review')
  setLocale('cs')
  await flushPromises()
  expect(openDialog()?.textContent).toContain('Schválit a mergovat PR M01-S01-T01 do main?')
  await answerDialog(false)
})

it.each(['conflict', 'trace_db_locked', 'pr_not_open', 'missing_note', 'unexpected_code'])(
  'translates an API action failure (%s) already on screen and keeps the draft', async (code) => {
    go('M01-S01-T01')
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST' ? fail(code) : ok(reviewDetail()))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ReviewView, { attachTo: document.body })
    await flushPromises()
    await wrapper.get('[data-test="return-note"]').setValue('Rozepsaná poznámka')
    await wrapper.get('[data-test="return"]').trigger('click')
    await answerDialog(true)
    await flushPromises()
    const english = wrapper.get('[data-test="error"]').text()
    expect(english).toContain('Return failed:')
    expect(english).not.toContain('Původní backendovou')
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(code === 'trace_db_locked')
    const requests = fetchMock.mock.calls.length
    setLocale('cs')
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toContain('Vrácení selhalo:')
    expect(wrapper.get('[data-test="error"]').text()).not.toBe(english)
    expect(wrapper.get('[data-test="return-note"]').element).toHaveProperty('value', 'Rozepsaná poznámka')
    expect(wrapper.find('[data-test="retry"]').exists()).toBe(code === 'trace_db_locked')
    setLocale('en')
    await flushPromises()
    expect(wrapper.get('[data-test="error"]').text()).toBe(english)
    expect(fetchMock.mock.calls.length).toBe(requests)
  },
)

it('translates detail loading and a no-PR API failure without a second request', async () => {
  go('M01-S01-T01')
  const response = deferred<Response>()
  const fetchMock = vi.fn(() => response.promise)
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ReviewView)
  expect(wrapper.get('[data-test="detail-loading"]').text()).toContain('Loading…')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="detail-loading"]').text()).toContain('Načítám…')
  response.resolve(fail('no_pr'))
  await flushPromises()
  expect(wrapper.get('[data-test="error"]').text()).toContain('Task M01-S01-T01 nemá PR.')
  setLocale('en')
  await flushPromises()
  expect(wrapper.get('[data-test="error"]').text()).toContain('Task M01-S01-T01 has no PR.')
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('translates conflict actions and empty checks, verdict and diff', async () => {
  const wrapper = mount(ReviewDetail, { props: {
    detail: reviewDetail({ mergeability: 'conflict', checks: [], review: null, runs: [],
      diff: { base: 'main', merge_base: null, stat: { files: 0, additions: 0, deletions: 0 }, files: [] },
      actions: { approve: false, return: true, resolve: true } }), busy: false,
  } })
  for (const section of wrapper.findAll('button.dsec-head')) await section.trigger('click')
  expect(wrapper.get('[data-test="resolve"]').text()).toBe('Resolve conflict with base')
  expect(wrapper.get('[data-test="approve"]').attributes('disabled')).toBeDefined()
  expect(wrapper.get('[data-test="no-checks"]').text()).toBe('No gates or tests have run')
  expect(wrapper.get('[data-test="no-verdict"]').text()).toBe('Review has not run')
  expect(wrapper.get('[data-test="no-diff"]').text()).toBe('No changes')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="resolve"]').text()).toBe('Vyřešit konflikt s base')
  expect(wrapper.get('[data-test="no-checks"]').text()).toBe('Gates ani testy neběžely')
  expect(wrapper.get('[data-test="no-verdict"]').text()).toBe('Review neběželo')
  expect(wrapper.get('[data-test="no-diff"]').text()).toBe('Žádné změny')
})

it.each([
  ['approve', 'merged', 'Merged', 'Sloučeno'],
  ['approve', 'background', 'Approval is running in the background', 'Schvalování běží na pozadí'],
  ['return', 'started', 'Started run', 'Spuštěn běh'],
  ['resolve', 'pending', 'Starting run…', 'Běh se spouští…'],
] as const)('translates a successful %s notice (%s) without repeating the action', async (action, outcome, en, cs) => {
  go('M01-S01-T01')
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      if (outcome === 'merged') return ok({ ok: true, merge_sha: 'abcdef123', approve_note: 'Legacy system note' })
      if (outcome === 'background') return ok({ action: 'approve', started: true })
      return ok({ action, task_id: 'M01-S01-T01', pending: outcome === 'pending',
        run: outcome === 'pending' ? null : { run_id: 'r-return', workflow: 'return', branch: 'factory/task' } })
    }
    return ok(url.endsWith('/review') ? reviewList() : reviewDetail())
  })
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(ReviewView, { attachTo: document.body })
  await flushPromises()
  if (action === 'return') await wrapper.get('[data-test="return-note"]').setValue('Obsah poznámky')
  await wrapper.get(`[data-test="${action}"]`).trigger('click')
  if (action !== 'resolve') await answerDialog(true)
  await flushPromises()
  expect(wrapper.text()).toContain(en)
  const requests = fetchMock.mock.calls.length
  setLocale('cs')
  await flushPromises()
  expect(wrapper.text()).toContain(cs)
  if (action === 'return') expect(wrapper.get('[data-test="return-note"]').element).toHaveProperty('value', '')
  setLocale('en')
  await flushPromises()
  expect(wrapper.text()).toContain(en)
  expect(fetchMock.mock.calls.length).toBe(requests)
})


it('keeps both action and reload failures reactive when the detail reload also fails', async () => {
  go('M01-S01-T01')
  let reads = 0
  vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === 'POST') return fail('pr_not_open')
    reads += 1
    return reads === 1 ? ok(reviewDetail()) : fail('request_timeout')
  }))
  const wrapper = mount(ReviewView, { attachTo: document.body })
  await flushPromises()
  await wrapper.get('[data-test="return-note"]').setValue('Přidej test')
  await wrapper.get('[data-test="return"]').trigger('click')
  await answerDialog(true)
  await flushPromises()
  const english = wrapper.get('[data-test="error"]').text()
  expect(english).toContain('Return failed: The PR is no longer open.')
  expect(english).toContain('Could not load the PR for task M01-S01-T01:')
  expect(english).toContain(' · ')
  setLocale('cs')
  await flushPromises()
  expect(wrapper.get('[data-test="error"]').text()).toContain('Vrácení selhalo: PR už není otevřené.')
  expect(wrapper.get('[data-test="error"]').text()).toContain('PR tasku M01-S01-T01 se nepodařilo načíst:')
  setLocale('en')
  await flushPromises()
  expect(wrapper.get('[data-test="error"]').text()).toBe(english)
  expect(reads).toBe(2)
})
