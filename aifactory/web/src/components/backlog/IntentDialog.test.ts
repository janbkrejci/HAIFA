import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import IntentDialog from './IntentDialog.vue'
import { chooseOption, selectLabels } from '@/test/select'
import type { IntentJob, Proposal } from '@/lib/intent'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({ ...(await original<object>()), ...api }))

const DONE = '\n\nHotovo znamená:\n- testy projdou'

function proposal(extra: Partial<Proposal> = {}): Proposal {
  return {
    summary: 'Dva tasky exportu.',
    applied: false,
    step: { id: 'P01-S02', title: 'Export', body: 'Export dat do CSV.', path: 'backlog/P01/S02-export', new: true },
    tasks: [
      { id: 'P01-S02-T01', code: 'T01', title: 'Model exportu', body: `Udělej model.${DONE}`, workflow: 'plan', writes: ['src/t01/'], depends_on: [], path: 'a.md' },
      { id: 'P01-S02-T02', code: 'T02', title: 'CLI exportu', body: `Udělej CLI.${DONE}`, workflow: 'plan', writes: ['src/t02/'], depends_on: ['P01-S02-T01'], path: 'b.md' },
    ],
    files: [],
    findings: [{ rule: 'writes_uncovered', task: 'P01-S02-T02', message: 'docs/x.md is not covered', blocking: false }],
    ...extra,
  }
}

function job(extra: Partial<IntentJob> = {}): IntentJob {
  return {
    job_id: 'intent-1', state: 'ready', round: 1, intent: 'Export do CSV', target: { project: 'P01' },
    proposal: proposal(), error: null, issues: [], notes: [], progress: [], applied: null, ...extra,
  }
}

const props = {
  projects: [{ id: 'P01', title: 'Projekt' }],
  steps: [{ id: 'P01-S01', title: 'Step', path: 'backlog/P01/S01', project: 'P01' }],
  pollMs: 1,
}

async function settle(): Promise<void> {
  for (let i = 0; i < 5; i++) {
    await new Promise((done) => setTimeout(done, 5))
    await flushPromises()
  }
}

async function proposed(wrapper: VueWrapper): Promise<void> {
  await wrapper.get('[data-test="intent-text"]').setValue('Export do CSV')
  await chooseOption(wrapper, '[data-test="intent-target"]', 'project:P01')
  await wrapper.get('[data-test="intent-propose"]').trigger('click')
  await settle()
}

beforeEach(() => {
  window.location.hash = '#/r/repo/backlog/intent'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  api.postApi.mockReset().mockImplementation(async (path: string) => {
    if (path === '/backlog/intent') return job({ state: 'running', proposal: null })
    if (path.endsWith('/refine')) return job({ state: 'queued', round: 2, proposal: null, notes: ['Přidej docs.'] })
    if (path.endsWith('/apply')) return { ...proposal(), applied: true, commit: { committed: true, commit: 'abc', base: 'main' }, warnings: [] }
    return {}
  })
  api.getApi.mockReset()
})
afterEach(() => {
  document.body.innerHTML = ''
})

describe('IntentDialog', () => {
  it('offers projects for a new step and steps for new tasks, preselecting the initial one', async () => {
    const wrapper = mount(IntentDialog, { props: { ...props, initial: 'P01-S01' } })
    expect(await selectLabels(wrapper, '[data-test="intent-target"]')).toEqual([
      'P01 – Projekt · nový step',
      'P01-S01 – Step · nové tasky',
    ])
    expect(wrapper.get('[data-test="intent-target"]').text()).toContain('P01-S01')
    expect(wrapper.get('[data-test="intent-propose"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="intent-text"]').setValue('Něco')
    expect(wrapper.get('[data-test="intent-propose"]').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('shows the progress, then the tree with texts and findings', async () => {
    let resolve!: (value: IntentJob) => void
    api.getApi.mockImplementationOnce(async () => job({ state: 'running', proposal: null, progress: [
      { kind: 'agent_start', text: 'Agent proposer pracuje', ts: '' },
      { kind: 'tool_call', text: 'Read src/app.py', ts: '' },
    ] }))
    api.getApi.mockImplementationOnce(() => new Promise((done) => { resolve = done }))
    const wrapper = mount(IntentDialog, { props })
    await proposed(wrapper)
    expect(api.postApi).toHaveBeenCalledWith('/backlog/intent', { intent: 'Export do CSV', project: 'P01' })
    const progress = wrapper.get('[data-test="intent-progress"]')
    expect(progress.text()).toContain('Agent navrhuje')
    expect(progress.text()).toContain('Read src/app.py')
    resolve(job())
    await settle()
    expect(wrapper.find('[data-test="intent-progress"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="intent-step"]').text()).toContain('P01-S02')
    const tasks = wrapper.findAll('[data-test="intent-task"]')
    expect(tasks.map((t) => t.attributes('data-task'))).toEqual(['P01-S02-T01', 'P01-S02-T02'])
    expect(tasks[1]!.text()).toContain('Udělej CLI.')
    expect(tasks[1]!.find('details').exists()).toBe(true)
    expect(tasks[1]!.get('[data-rule="writes_uncovered"]').text()).toContain('docs/x.md')
    expect(wrapper.get('[data-test="intent-findings-count"]').text()).toContain('1 nález')
    wrapper.unmount()
  })

  it('removes and edits tasks, refines with a note, and applies what is kept', async () => {
    api.getApi.mockResolvedValueOnce(job())
    const wrapper = mount(IntentDialog, { props })
    await proposed(wrapper)
    const tasks = () => wrapper.findAll('[data-test="intent-task"]')
    await tasks()[0]!.get('[data-test="intent-task-edit"]').trigger('click')
    await tasks()[0]!.get('[data-test="intent-task-title"]').setValue('Model CSV')
    await tasks()[0]!.get('[data-test="intent-task-body"]').setValue(`Jinak.${DONE}`)
    await tasks()[1]!.get('[data-test="intent-task-remove"]').trigger('click')
    expect(tasks()[1]!.classes()).toContain('removed')
    expect(wrapper.get('[data-test="intent-apply"]').text()).toContain('Použít (1)')

    expect(wrapper.get('[data-test="intent-refine"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="intent-note"]').setValue('Přidej docs.')
    api.getApi.mockResolvedValueOnce(job({ round: 2, notes: ['Přidej docs.'] }))
    await wrapper.get('[data-test="intent-refine"]').trigger('click')
    await settle()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/intent/intent-1/refine', {
      note: 'Přidej docs.',
      tasks: [{ code: 'T01', title: 'Model CSV', body: `Jinak.${DONE}` }],
    })
    // the revised proposal replaces the edits
    expect(tasks()).toHaveLength(2)
    expect(tasks()[1]!.classes()).not.toContain('removed')
    expect(wrapper.get('[data-test="intent-notes"]').text()).toContain('Přidej docs.')

    await tasks()[0]!.get('[data-test="intent-task-remove"]').trigger('click')
    await wrapper.get('[data-test="intent-apply"]').trigger('click')
    await settle()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/intent/intent-1/apply', {
      tasks: [{ code: 'T02', title: 'CLI exportu', body: `Udělej CLI.${DONE}` }],
    })
    const applied = wrapper.emitted('applied')?.[0]?.[0] as Proposal
    expect(applied.applied).toBe(true)
    expect(wrapper.get('[data-test="intent-applied"]').text()).toContain('commitnutý do main')
    wrapper.unmount()
    expect(api.postApi).not.toHaveBeenCalledWith('/backlog/intent/intent-1/discard')
  })

  it('shows a failed proposal and an apply error; Zrušit discards the job', async () => {
    api.getApi.mockResolvedValueOnce(job({ state: 'failed', proposal: null, error: 'proposal rejected', issues: [
      { code: 'unknown_workflow', message: 'unknown workflow', path: null, id: null },
    ] }))
    const wrapper = mount(IntentDialog, { props })
    await proposed(wrapper)
    expect(wrapper.text()).toContain('proposal rejected')
    expect(wrapper.find('[data-issue="unknown_workflow"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="intent-result"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="intent-propose"]').text()).toBe('Navrhnout znovu')

    api.getApi.mockResolvedValueOnce(job())
    await wrapper.get('[data-test="intent-propose"]').trigger('click')
    await settle()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/intent/intent-1/discard')
    const { ApiError } = await import('@/lib/api')
    api.postApi.mockRejectedValueOnce(new ApiError('backlog_invalid', 'proposal rejected: 1 problem(s)', [
      { code: 'unknown_ref', message: 'no task P01-S09-T01', path: null, id: null },
    ]))
    await wrapper.get('[data-test="intent-apply"]').trigger('click')
    await settle()
    expect(wrapper.find('[data-issue="unknown_ref"]').exists()).toBe(true)
    expect(wrapper.emitted('applied')).toBeUndefined()

    api.postApi.mockClear()
    await wrapper.get('[data-test="intent-cancel"]').trigger('click')
    expect(api.postApi).toHaveBeenCalledWith('/backlog/intent/intent-1/discard')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    wrapper.unmount()
  })
})
