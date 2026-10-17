import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import ActionCard from './ActionCard.vue'
import { resetAssistantForTests, type ProposedAction } from '@/lib/assistant'

function envelope(data: unknown, status = 200) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }), { status })
}

const FOLLOW_UP: ProposedAction = {
  id: 'f1',
  kind: 'follow_up',
  repo: 'haifa',
  task: 'P01-S01-T01',
  body: 'Dodělat dokumentaci.',
  run: true,
  reason: 'Task je hotový, docs chybí.',
  status: 'proposed',
}

function stubApi() {
  const posted: { url: string; body: unknown }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      if (init?.method === 'POST') posted.push({ url, body })
      if (url === '/api/repos/haifa/backlog/tasks/P01-S01-T01') {
        const task = {
          title: 'First',
          writes: ['src/', 'docs/'],
          own_writes: ['src/'],
          workflow: 'custom',
          own_workflow: 'custom',
          status: 'done',
        }
        return envelope({ task, body: 'Body' })
      }
      if (url.endsWith('/follow-up')) return envelope({ task: { id: 'P01-S01-T02' }, run: { run_id: 'abcd1234' } }, 202)
      if (url.includes('/actions/')) {
        const action = { ...FOLLOW_UP, status: body.status, outcome: { message: body.message, at: '' } }
        return envelope({ action, message: { id: 'n1', role: 'action', text: 'x', action_id: 'f1', status: body.status } })
      }
      return envelope({})
    }),
  )
  return posted
}

enableAutoUnmount(afterEach)

afterEach(() => {
  resetAssistantForTests()
  vi.unstubAllGlobals()
})

describe('ActionCard follow_up', () => {
  it('previews the takeover of writes and workflow and writes nothing until Provést', async () => {
    const posted = stubApi()
    const action = { ...FOLLOW_UP }
    const wrapper = mount(ActionCard, { props: { action, threadId: 'a1b2c3d4e5f6' } })
    await flushPromises()

    expect(wrapper.get('[data-test="assistant-action-title"]').text()).toBe('Navázat follow-upem na P01-S01-T01')
    const preview = wrapper.get('[data-test="assistant-action-preview"]').text()
    expect(preview).toContain('Navazuje na P01-S01-T01: First')
    expect(preview).toContain('Writes')
    expect(preview).toContain('src/')
    expect(preview).not.toContain('docs/')
    expect(preview).toContain('custom')
    expect(preview).toContain('Dodělat dokumentaci.')
    expect(preview).toContain('commitnout backlog a spustit')
    expect(posted).toEqual([])

    await wrapper.get('[data-test="assistant-action-run"]').trigger('click')
    await flushPromises()
    expect(posted[0]).toEqual({
      url: '/api/repos/haifa/backlog/tasks/P01-S01-T01/follow-up',
      body: { body: 'Dodělat dokumentaci.', run: true },
    })
    expect(posted[1]!.url).toBe('/api/assistant/threads/a1b2c3d4e5f6/actions/f1')
    expect(posted[1]!.body).toEqual({ status: 'done', message: 'Task P01-S01-T02 založen. Běh abcd1234 spuštěn.' })
  })

  it('dismissed, it calls no write API', async () => {
    const posted = stubApi()
    const wrapper = mount(ActionCard, { props: { action: { ...FOLLOW_UP }, threadId: 'a1b2c3d4e5f6' } })
    await flushPromises()
    await wrapper.get('[data-test="assistant-action-dismiss"]').trigger('click')
    await flushPromises()
    expect(posted.map((p) => p.url)).toEqual(['/api/assistant/threads/a1b2c3d4e5f6/actions/f1'])
  })
})
