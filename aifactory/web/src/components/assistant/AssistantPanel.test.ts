import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import AssistantPanel from './AssistantPanel.vue'
import { assistant, resetAssistantForTests, setOpen } from '@/lib/assistant'
import { FakeEventSource } from '@/test/fakeEventSource'

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

function failure(code: string, message: string, status: number) {
  return new Response(JSON.stringify({ ok: false, data: null, error: { code, message }, warnings: [] }), { status })
}

const THREAD = {
  id: 'a1b2c3d4e5f6',
  title: '',
  harness: 'claude',
  model: 'claude-opus-5-5',
  created_at: '2026-10-16T10:00:00+00:00',
  updated_at: '2026-10-16T10:00:00+00:00',
  busy: false,
  messages: [],
  seq: 0,
}

const PROPOSAL = {
  id: 'p1',
  kind: 'edit_task',
  repo: 'haifa',
  task: 'P01-S01-T01',
  writes: ['src/', 'docs/'],
  reason: 'Task píše i do docs.',
  status: 'proposed',
}

const WITH_PROPOSAL = {
  ...THREAD,
  messages: [
    { id: 'm1', role: 'user', text: 'Uprav writes', screen: {} },
    { id: 'm2', role: 'assistant', text: 'Navrhuji změnu.', actions: [PROPOSAL] },
  ],
}

interface Sent {
  url: string
  body: unknown
}

function stubApi(
  options: { runState?: string; threads?: unknown[]; detail?: unknown; busy?: boolean; deleteBusy?: boolean } = {},
) {
  const sent: Sent[] = []
  const deleted: string[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(String(init.body)) : undefined
    if (init?.method === 'POST') sent.push({ url, body })
    if (url === '/api/repos/haifa/backlog/tasks/P01-S01-T01') {
      return envelope({ task: { title: 'First', writes: ['src/'], workflow: null, status: 'todo' }, body: 'Body' })
    }
    if (url === '/api/repos/haifa/backlog/tasks/P01-S01-T01/edit') return envelope({ changed: true, task: {} })
    if (url.includes('/actions/')) {
      const action = { ...PROPOSAL, status: body.status, outcome: { message: body.message, at: '' } }
      const message = { id: 'n1', role: 'action', text: 'x', action_id: PROPOSAL.id, status: body.status }
      return envelope({ action, message })
    }
    if (url.startsWith('/api/repos/haifa/runs/')) return envelope({ run: { state: options.runState ?? 'failed' } })
    if (url === '/api/assistant/threads' && init?.method === 'POST') return envelope(THREAD, 201)
    if (url === '/api/assistant/threads') return envelope({ threads: options.threads ?? [] })
    if (url.endsWith('/messages')) {
      if (options.busy) return failure('busy', 'the guide is still answering in this thread', 409)
      const message = { id: 'm1', role: 'user', text: body.text, screen: body.screen ?? {}, at: THREAD.created_at }
      return envelope({ thread: { ...THREAD, title: body.text, busy: true, messages: 1 }, message, seq: 1 }, 202)
    }
    if (url.startsWith('/api/assistant/threads/') && init?.method === 'DELETE') {
      if (options.deleteBusy) return failure('busy', 'the guide is still answering in this thread', 409)
      deleted.push(url)
      return envelope({ deleted: url.split('/').pop() })
    }
    if (url.startsWith('/api/assistant/threads/')) return envelope(options.detail ?? THREAD)
    return envelope({})
  })
  vi.stubGlobal('fetch', fetchMock)
  return { fetchMock, sent, deleted }
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

enableAutoUnmount(afterEach)

beforeEach(() => {
  vi.stubGlobal('EventSource', FakeEventSource)
})

afterEach(() => {
  resetAssistantForTests()
  FakeEventSource.reset()
  vi.unstubAllGlobals()
})

async function openPanel() {
  setOpen(true)
  const wrapper = mount(AssistantPanel, { props: { repos: ['haifa', 'other'] } })
  await flushPromises()
  return wrapper
}

describe('AssistantPanel', () => {
  it('offers why a failed run failed, with the run as a context chip', async () => {
    stubApi({ runState: 'failed' })
    go('#/r/haifa/runs/740183f7')
    const wrapper = await openPanel()
    expect(wrapper.get('[data-test="assistant-context"]').text()).toContain('repo haifa · běh 740183f7')
    const offered = wrapper.findAll('[data-test="assistant-suggestion"]').map((b) => b.text())
    expect(offered).toHaveLength(3)
    expect(offered[0]).toBe('Proč tenhle běh selhal?')
  })

  it('streams the answer as markdown with dashboard links', async () => {
    const { sent } = stubApi()
    go('#/r/haifa/runs/740183f7')
    const wrapper = await openPanel()
    await wrapper.findAll('[data-test="assistant-suggestion"]')[0]!.trigger('click')
    await flushPromises()

    expect(sent.map((s) => s.url)).toEqual(['/api/assistant/threads', '/api/assistant/threads/a1b2c3d4e5f6/messages'])
    expect(sent[1]!.body).toEqual({ text: 'Proč tenhle běh selhal?', screen: { repo: 'haifa', run: '740183f7' } })
    const stream = FakeEventSource.latest()
    expect(stream.url).toBe('/api/assistant/threads/a1b2c3d4e5f6/stream?after=1')
    expect(wrapper.get('[data-test="assistant-harness"]').text()).toBe('claude · claude-opus-5-5')

    stream.emit('tool', { seq: 2, label: './guide sql haifa "SELECT …"' })
    stream.emit('text', { seq: 3, text: 'Task **P01-S01-T01** selhal v testech.' })
    await flushPromises()
    const streaming = wrapper.get('[data-test="assistant-streaming"]')
    expect(streaming.text()).toContain('./guide sql haifa')
    expect(streaming.find('strong').exists()).toBe(true)

    const answer = { id: 'm2', role: 'assistant', text: 'Task `P01-S01-T01` selhal, viz PR #4.', at: THREAD.created_at }
    stream.emit('done', { seq: 4, message: answer })
    await flushPromises()
    expect(stream.closed).toBe(true)
    expect(wrapper.find('[data-test="assistant-streaming"]').exists()).toBe(false)
    const links = wrapper.get('[data-test="assistant-answer"]').findAll('a').map((a) => a.attributes('href'))
    expect(links).toEqual(['#/r/haifa/backlog/P01-S01-T01', '#/r/haifa/review'])
  })

  it('keeps the open thread when the screen changes', async () => {
    stubApi()
    go('#/r/haifa/runs/740183f7')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-input"]').setValue('Co se stalo?')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    FakeEventSource.latest().emit('done', { seq: 2, message: { id: 'm2', role: 'assistant', text: 'Nic.' } })
    go('#/r/haifa/backlog/P01-S01-T01')
    await flushPromises()
    expect(wrapper.findAll('[data-test="assistant-user"]')).toHaveLength(1)
    expect(wrapper.get('[data-test="assistant-answer"]').text()).toBe('Nic.')
    expect(wrapper.get('[data-test="assistant-context"]').text()).toContain('task P01-S01-T01')
  })

  it('sends without the screen once the chip is removed', async () => {
    const { sent } = stubApi()
    go('#/r/haifa/backlog/P01-S01-T01')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-context-remove"]').trigger('click')
    expect(wrapper.find('[data-test="assistant-context"]').exists()).toBe(false)
    await wrapper.get('[data-test="assistant-input"]').setValue('Co dál?')
    await wrapper.get('[data-test="assistant-input"]').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(sent[1]!.body).toEqual({ text: 'Co dál?' })
    // another screen brings its own chip back
    go('#/r/haifa/backlog/P01-S01-T02')
    await flushPromises()
    expect(wrapper.get('[data-test="assistant-context"]').text()).toContain('P01-S01-T02')
  })

  it('lists older threads and opens one', async () => {
    const older = { ...THREAD, id: 'ffffffffffff', title: 'Co běží?', harness: 'codex', model: 'gpt-5.5', messages: 2 }
    const detail = {
      ...older,
      messages: [
        { id: 'u', role: 'user', text: 'Co běží?', screen: {} },
        { id: 'a', role: 'assistant', text: 'Nic neběží.' },
      ],
    }
    stubApi({ threads: [older], detail })
    go('#/overview')
    const wrapper = await openPanel()
    expect(wrapper.find('[data-test="assistant-context"]').exists()).toBe(false)
    await wrapper.get('[data-test="assistant-threads"]').trigger('click')
    await flushPromises()
    const items = wrapper.findAll('[data-test="assistant-thread-item"]')
    expect(items).toHaveLength(1)
    expect(items[0]!.text()).toContain('codex · gpt-5.5')
    await items[0]!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="assistant-answer"]').text()).toBe('Nic neběží.')
    expect(wrapper.get('[data-test="assistant-harness"]').text()).toBe('codex · gpt-5.5')
    expect(assistant.thread?.id).toBe('ffffffffffff')

    await wrapper.get('[data-test="assistant-new"]').trigger('click')
    expect(wrapper.findAll('[data-test="assistant-suggestion"]')).toHaveLength(3)
  })

  it('shows an answer that failed and a refused message', async () => {
    stubApi({ busy: true })
    go('#/overview')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-input"]').setValue('Ahoj')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[data-test="assistant-error"]').text()).toContain('still answering')
  })

  it('follows an answer still running when a thread is opened', async () => {
    const detail = { ...THREAD, busy: true, messages: [{ id: 'u', role: 'user', text: 'Co běží?' }], seq: 3 }
    stubApi({ detail })
    const wrapper = await openPanel()
    resetAssistantForTests()
    sessionStorage.setItem('haifa.assistant.thread', THREAD.id)
    setOpen(true)
    await flushPromises()
    expect(FakeEventSource.latest().url).toBe('/api/assistant/threads/a1b2c3d4e5f6/stream?after=0')
    FakeEventSource.latest().emit('error', { seq: 4, message: { id: 'e', role: 'assistant', text: '', error: 'agent exited 1' } })
    await flushPromises()
    expect(wrapper.get('[data-test="assistant-answer-error"]').text()).toBe('agent exited 1')
  })

  it('shows a proposed action as a card and writes only after Provést', async () => {
    window.sessionStorage.setItem('haifa.assistant.thread', THREAD.id)
    const { sent } = stubApi({ detail: structuredClone(WITH_PROPOSAL) })
    go('#/r/haifa/backlog')
    const wrapper = await openPanel()
    const card = wrapper.get('[data-test="assistant-action"]')
    expect(card.get('[data-test="assistant-action-title"]').text()).toBe('Upravit task P01-S01-T01')
    expect(card.get('[data-test="assistant-action-preview"]').text()).toContain('src/, docs/')
    expect(card.text()).toContain('Task píše i do docs.')
    expect(sent).toEqual([])

    await card.get('[data-test="assistant-action-run"]').trigger('click')
    await flushPromises()
    expect(sent.map((s) => s.url)).toEqual([
      '/api/repos/haifa/backlog/tasks/P01-S01-T01/edit',
      `/api/assistant/threads/${THREAD.id}/actions/p1`,
    ])
    expect(sent[0]?.body).toEqual({ writes: ['src/', 'docs/'] })
    expect(sent[1]?.body).toEqual({ status: 'done', message: 'Task upraven.' })
    expect(wrapper.find('[data-test="assistant-action-run"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="assistant-action-state"]').text()).toBe('Provedeno: Task upraven.')
    expect(wrapper.get('[data-test="assistant-outcome"]').text()).toContain('provedeno')
  })

  it('dismisses a proposal without calling the write API', async () => {
    window.sessionStorage.setItem('haifa.assistant.thread', THREAD.id)
    const { sent } = stubApi({ detail: structuredClone(WITH_PROPOSAL) })
    go('#/r/haifa/backlog')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-action-dismiss"]').trigger('click')
    await flushPromises()
    expect(sent.map((s) => s.url)).toEqual([`/api/assistant/threads/${THREAD.id}/actions/p1`])
    expect(wrapper.get('[data-test="assistant-action-state"]').text()).toBe('Zahozeno')
  })

  it('deletes an older thread only after the confirmation', async () => {
    const older = { ...THREAD, id: 'ffffffffffff', title: 'Co běží?', messages: 2 }
    const { deleted } = stubApi({ threads: [older] })
    go('#/overview')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-threads"]').trigger('click')
    await flushPromises()

    await wrapper.get('[data-test="assistant-thread-delete"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-test="confirm-message"]')?.textContent).toContain('Co běží?')
    ;(document.body.querySelector('[data-test="confirm-cancel"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(deleted).toEqual([])
    expect(wrapper.findAll('[data-test="assistant-thread-item"]')).toHaveLength(1)

    await wrapper.get('[data-test="assistant-thread-delete"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-test="confirm-ok"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(deleted).toEqual(['/api/assistant/threads/ffffffffffff'])
    expect(wrapper.find('[data-test="assistant-thread-item"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="assistant-no-threads"]').exists()).toBe(true)
  })

  it('leaves a deleted open thread for an empty one', async () => {
    window.sessionStorage.setItem('haifa.assistant.thread', THREAD.id)
    const detail = { ...THREAD, title: 'Otevřené', messages: [{ id: 'u', role: 'user', text: 'Ahoj', screen: {} }] }
    const { deleted } = stubApi({ threads: [{ ...THREAD, title: 'Otevřené', messages: 1 }], detail })
    go('#/overview')
    const wrapper = await openPanel()
    expect(assistant.thread?.id).toBe(THREAD.id)
    await wrapper.get('[data-test="assistant-threads"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="assistant-thread-delete"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-test="confirm-ok"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(deleted).toEqual([`/api/assistant/threads/${THREAD.id}`])
    expect(assistant.thread).toBeNull()
    expect(window.sessionStorage.getItem('haifa.assistant.thread')).toBeNull()

    await wrapper.get('[data-test="assistant-threads"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="assistant-user"]').exists()).toBe(false)
    expect(wrapper.findAll('[data-test="assistant-suggestion"]')).toHaveLength(3)
  })

  it('shows why a thread could not be deleted and keeps it', async () => {
    const older = { ...THREAD, id: 'ffffffffffff', title: 'Co běží?', busy: true, messages: 1 }
    stubApi({ threads: [older], deleteBusy: true })
    go('#/overview')
    const wrapper = await openPanel()
    await wrapper.get('[data-test="assistant-threads"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="assistant-thread-delete"]').trigger('click')
    await flushPromises()
    ;(document.body.querySelector('[data-test="confirm-ok"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(wrapper.get('[data-test="assistant-threads-error"]').text()).toContain('still answering')
    expect(wrapper.findAll('[data-test="assistant-thread-item"]')).toHaveLength(1)
  })
})
