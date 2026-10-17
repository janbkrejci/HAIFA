import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import LessonsSection from './LessonsSection.vue'
import type { Lesson, LearnState, LessonScan } from '@/lib/learn'
import { resetNames, setNames } from '@/lib/names'
import { chooseOption } from '@/test/select'

enableAutoUnmount(afterEach)

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function failed(code: string, status = 409) {
  return new Response(
    JSON.stringify({ ok: false, data: null, error: { code, message: `${code} message`, path: null, id: null, issues: [] }, warnings: [] }),
    { status },
  )
}

function lesson(extra: Partial<Lesson> = {}): Lesson {
  return {
    id: 'L1',
    rule: 'Add a test for every new CLI command.',
    target: 'AGENTS.md',
    target_detail: '',
    state: 'proposed',
    reason: null,
    task_id: null,
    occurrences: 2,
    runs: [{ run_id: 'run-a', task_id: 'P01-S01-T01' }, { run_id: 'run-b', task_id: 'P01-S01-T02' }],
    complaints: [
      { run_id: 'run-a', task_id: 'P01-S01-T01', source: 'review', phase: 'review', text: 'The new CLI command has no test.', created_at: '2026-10-02T10:00:00Z' },
      { run_id: 'run-b', task_id: 'P01-S01-T02', source: 'test_triage', phase: 'test', text: 'no test for x', created_at: '2026-10-05T10:00:00Z' },
    ],
    pr: null,
    effect: null,
    ...extra,
  }
}

const DONE: LessonScan = {
  state: 'done', since: null, started_at: '2026-10-10T10:00:00Z', finished_at: '2026-10-10T10:01:00Z',
  result: { objections: 3, runs: 2, lessons: 1, repeats: 0 }, error: null,
}

/** Answers of GET /learn in order (the last one repeats) and the POSTs seen. */
function stub(states: LearnState[], post: (url: string, body: unknown) => Response = () => ok({})) {
  const posts: [string, unknown][] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (init?.method === 'POST') {
      const body = init.body ? JSON.parse(String(init.body)) : null
      posts.push([url.replace('/api/repos/a', ''), body])
      return post(url, body)
    }
    if (url === '/api/repos/a/learn') return ok(states.length > 1 ? states.shift() : states[0])
    throw new Error(`unexpected ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return posts
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) {
    await new Promise((done) => setTimeout(done, 5))
    await flushPromises()
  }
}

beforeEach(() => {
  window.location.hash = '#/r/a/factory'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  resetNames()
})
afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

describe('LessonsSection', () => {
  it('shows a proposed lesson with its rule, target and runs', async () => {
    stub([{ lessons: [lesson({ target: 'skill', target_detail: 'release' })], scan: DONE }])
    const wrapper = mount(LessonsSection, { attachTo: document.body })
    await settle()
    const card = wrapper.get('[data-lesson="L1"]')
    expect(card.get('[data-test="lesson-rule"]').text()).toBe('Add a test for every new CLI command.')
    expect(card.get('[data-test="lesson-target"]').text()).toBe('skill release')
    expect(card.get('[data-test="lesson-occurrences"]').text()).toBe('2 běhy')
    const runs = card.findAll('[data-test="lesson-run"]')
    expect(runs.map((r) => r.text())).toEqual(['run-a', 'run-b'])
    expect(runs[0]!.attributes('href')).toBe('#/r/a/runs/run-a')
    expect(card.text()).toContain('triáž testů')
    expect(wrapper.get('[data-test="lessons-scan-done"]').text()).toContain('3 výtek z 2 běhy')
  })

  it('says there are no lessons yet', async () => {
    stub([{ lessons: [], scan: null }])
    const wrapper = mount(LessonsSection)
    await settle()
    expect(wrapper.get('[data-test="lessons-empty"]').text()).toContain('Zatím žádné lekce')
  })

  it('starts a scan and polls until it ends', async () => {
    const running: LessonScan = { ...DONE, state: 'running', finished_at: null, result: null }
    const posts = stub(
      [{ lessons: [], scan: null }, { lessons: [], scan: running }, { lessons: [lesson()], scan: DONE }],
      () => ok(running),
    )
    const wrapper = mount(LessonsSection, { props: { pollMs: 1 } })
    await settle()
    await wrapper.get('[data-test="lessons-scan"]').trigger('click')
    await flushPromises()
    expect(posts).toEqual([['/learn/scan', {}]])
    await settle()
    expect(wrapper.find('[data-test="lessons-scanning"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="lesson"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="lessons-scan"]').attributes('disabled')).toBeUndefined()
  })

  it('shows a failed scan', async () => {
    stub([{ lessons: [], scan: { ...DONE, state: 'failed', result: null, error: 'learner harness unavailable' } }])
    const wrapper = mount(LessonsSection)
    await settle()
    expect(wrapper.get('[data-test="lessons-scan-error"]').text()).toBe('learner harness unavailable')
  })

  it('accepts a lesson and shows the task', async () => {
    const accepted = lesson({ state: 'accepted', task_id: 'P01-LEARN-T01' })
    const posts = stub([{ lessons: [lesson()], scan: null }, { lessons: [accepted], scan: null }], () =>
      ok({ id: 'L1', state: 'accepted', task: { id: 'P01-LEARN-T01' }, existed: false, committed: true }),
    )
    const wrapper = mount(LessonsSection)
    await settle()
    await wrapper.get('[data-test="lesson-accept"]').trigger('click')
    await settle()
    expect(posts).toEqual([['/learn/lessons/L1/accept', {}]])
    expect(wrapper.get('[data-test="lessons-notice"]').text()).toContain('task P01-LEARN-T01, commitnutý do base')
    const card = wrapper.get('[data-state="accepted"]')
    expect(card.get('[data-test="lesson-task"]').attributes('href')).toBe('#/r/a/backlog/P01-LEARN-T01')
    expect(card.get('[data-test="lesson-waiting"]').text()).toContain('po merge PR')
  })

  it('asks for the project when the runs do not tell it', async () => {
    setNames({ levels: ['project', 'step', 'task'], names: { P01: { title: 'Jádro', level: 'project' }, P02: { title: 'Web', level: 'project' }, 'P01-S01': { title: 's', level: 'step' } } })
    let first = true
    const posts = stub([{ lessons: [lesson()], scan: null }], () => {
      if (first) { first = false; return failed('project_required') }
      return ok({ id: 'L1', state: 'accepted', task: { id: 'P02-LEARN-T01' }, existed: false, committed: true })
    })
    const wrapper = mount(LessonsSection, { attachTo: document.body })
    await settle()
    await wrapper.get('[data-test="lesson-accept"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-test="lessons-error"]').exists()).toBe(false)
    await chooseOption(wrapper, '[data-test="lesson-project-select"]', 'P02')
    await wrapper.get('[data-test="lesson-project-accept"]').trigger('click')
    await settle()
    expect(posts).toEqual([['/learn/lessons/L1/accept', {}], ['/learn/lessons/L1/accept', { project: 'P02' }]])
    expect(wrapper.find('[data-test="lesson-project"]').exists()).toBe(false)
  })

  it('dismisses a lesson', async () => {
    const posts = stub(
      [{ lessons: [lesson()], scan: null }, { lessons: [lesson({ state: 'rejected' })], scan: null }],
      () => ok({ id: 'L1', state: 'rejected' }),
    )
    const wrapper = mount(LessonsSection)
    await settle()
    await wrapper.get('[data-test="lesson-dismiss"]').trigger('click')
    await settle()
    expect(posts).toEqual([['/learn/lessons/L1/dismiss', {}]])
    expect(wrapper.find('[data-test="lesson-accept"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="lessons-rejected"]').text()).toContain('Zamítnuté (1)')
  })

  it('shows the runs before and after the merge of an accepted lesson', async () => {
    const accepted = lesson({
      state: 'accepted', task_id: 'P01-LEARN-T01', occurrences: 3,
      pr: { url: 'https://example.test/pr/1', state: 'merged', merged_at: '2026-10-07T10:00:00Z' },
      effect: { merged_at: '2026-10-07T10:00:00Z', before: { runs: 2, objections: 2 }, after: { runs: 1, objections: 1 } },
    })
    stub([{ lessons: [accepted], scan: null }])
    const wrapper = mount(LessonsSection)
    await settle()
    expect(wrapper.get('[data-test="lesson-before"]').text()).toBe('2 bězích')
    expect(wrapper.get('[data-test="lesson-after"]').text()).toBe('1 běhu')
    expect(wrapper.find('[data-test="lesson-accept"]').exists()).toBe(false)
  })

  it('shows an error of the request', async () => {
    stub([{ lessons: [lesson()], scan: null }], () => failed('commit_failed', 500))
    const wrapper = mount(LessonsSection)
    await settle()
    await wrapper.get('[data-test="lesson-accept"]').trigger('click')
    await settle()
    expect(wrapper.get('[data-test="lessons-error"]').text()).toContain('commit_failed message')
  })
})
