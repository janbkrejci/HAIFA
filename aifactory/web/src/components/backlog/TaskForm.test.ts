import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskForm from './TaskForm.vue'
import { backlogData, taskNode } from '@/test/backlogFixtures'
import { chooseOption, selectLabels } from '@/test/select'
import { resetNamesForTests, setNames } from '@/lib/names'
import { confirmLeave, hasUnsavedChanges, leaveDialog } from '@/lib/leaveGuard'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)
beforeEach(() => {
  api.postApi.mockReset().mockResolvedValue({ job_id: 'edit-job' })
  api.getApi.mockReset().mockResolvedValue({
    state: 'succeeded', recommendation: {
      decision: 'existing', workflow_name: 'plan', workflow_yaml: null,
      reason: 'Analysis first', outline: [{ name: 'plan' }],
    },
  })
})

afterEach(() => {
  document.body.innerHTML = ''
  resetNamesForTests()
})

const data = backlogData()

function addForm(over = {}) {
  return mount(TaskForm, {
    props: { mode: 'add', steps: data.steps, workflows: data.workflows, busy: false, error: null, ...over },
  })
}

function editForm(over = {}) {
  return mount(TaskForm, {
    props: {
      mode: 'edit',
      steps: [],
      workflows: data.workflows,
      task: taskNode(over),
      busy: false,
      error: null,
    },
  })
}

describe('TaskForm', () => {
  it.each([
    ['approved', '[data-test="improve"]', '/backlog/task-advice'],
    ['approved', '[data-test="workflow-advice"] button', '/backlog/workflow-advice'],
    ['ready', '[data-test="improve"]', '/backlog/task-advice'],
    ['ready', '[data-test="workflow-advice"] button', '/backlog/workflow-advice'],
  ] as const)('gates %s task action %s before requesting advice', async (state, selector, endpoint) => {
    api.getApi.mockResolvedValue({ state: 'running' })
    const wrapper = editForm({ board_state: state, title: 'Valid task', own_workflow: 'plan' })
    try {
      await flushPromises()
      expect(wrapper.get('[data-test="title"]').element).toHaveProperty('value', 'Valid task')
      const button = wrapper.get(selector)
      expect(button.attributes('disabled') !== undefined).toBe(state === 'approved')
      await button.trigger('click')
      await flushPromises()
      if (state === 'approved') {
        expect(api.postApi).not.toHaveBeenCalled()
        expect(api.getApi).not.toHaveBeenCalled()
      } else {
        expect(api.postApi.mock.calls.map((call) => call[0])).toEqual([endpoint])
      }
    } finally {
      wrapper.unmount()
    }
  })

  it('sends the live edit draft and saves the recommendation without clearing inherited fields', async () => {
    const task = taskNode({ own_workflow: 'plan', own_writes: [], own_auto_merge: null })
    const wrapper = mount(TaskForm, { props: {
      mode: 'edit', steps: [], workflows: data.workflows, task,
      taskBody: 'Stored instructions', busy: false, error: null,
    } })
    await wrapper.get('[data-test="title"]').setValue('Updated draft')
    await wrapper.get('[data-test="workflow-advice"] button').trigger('click')
    await flushPromises()
    expect(api.postApi.mock.calls[0]?.[1]).toEqual({ task_id: task.id, draft: {
      title: 'Updated draft', body: 'Stored instructions', depends_on: task.depends_on,
      related: task.related, workflow: 'plan', writes: null,
    } })
    await wrapper.get('form').trigger('submit')
    // Saving a result with the same workflow name still sends its reference.
    expect(wrapper.emitted('submit')?.[0]).toEqual([{
      title: 'Updated draft', workflow: 'plan', workflow_advice_id: 'edit-job',
    }])
    await chooseOption(wrapper, '[data-test="workflow"]', '')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[1]).toEqual([{ title: 'Updated draft', clear_workflow: true }])
    wrapper.unmount()
  })

  it('emits a new task without empty fields', async () => {
    setNames({ names: {
      'M01-S01-T01': { title: 'Schema', level: 'task' },
      'M01-S01-T02': { title: 'API', level: 'task' },
    } })
    const wrapper = addForm()
    await chooseOption(wrapper, '[data-test="step"]', 'M02-S01')
    await wrapper.find('[data-test="title"]').setValue(' Filtr ')
    await wrapper.find('[data-test="writes"]').setValue('web/src/\n\nweb/test/\n')
    await chooseOption(wrapper, '[data-test="depends"]', 'M01-S01-T01')
    await chooseOption(wrapper, '[data-test="depends"]', 'M01-S01-T02')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([
      {
        step: 'M02-S01',
        title: 'Filtr',
        writes: ['web/src/', 'web/test/'],
        depends_on: ['M01-S01-T01', 'M01-S01-T02'],
      },
    ])
  })

  it('picks the links from the backlog codes, never the task itself', async () => {
    setNames({ names: {
      M01: { title: 'Projekt', level: 'project' },
      'M01-S01': { title: 'Step', level: 'step' },
      'M01-S01-T01': { title: 'Schema', level: 'task' },
      'M01-S01-T02': { title: 'API', level: 'task' },
    } })
    const wrapper = editForm({ id: 'M01-S01-T02', depends_on: ['M01-S01-T01'], related: [] })
    expect(await selectLabels(wrapper, '[data-test="related"]')).toEqual(['M01 · Projekt', 'M01-S01 · Step', 'M01-S01-T01 · Schema'])
    await chooseOption(wrapper, '[data-test="related"]', 'M01-S01-T01')
    await wrapper.get('[data-test="unpick-M01-S01-T01"]').trigger('click')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ depends_on: [], related: ['M01-S01-T01'] }])
    wrapper.unmount()
  })

  it('adds a blocking task in edit through the search dialog, never the task itself or a chosen one', async () => {
    setNames({ names: {
      M01: { title: 'Projekt', level: 'project' },
      'M01-S01-T01': { title: 'Schema', level: 'task' },
      'M01-S01-T02': { title: 'API', level: 'task' },
      'M01-S01-T03': { title: 'Loader', level: 'task' },
    } })
    const wrapper = mount(TaskForm, {
      props: { mode: 'edit', steps: [], workflows: data.workflows, busy: false, error: null,
        task: taskNode({ id: 'M01-S01-T02', depends_on: ['M01-S01-T01'], related: [] }) },
      attachTo: document.body,
    })
    await wrapper.get('[data-test="depends"]').trigger('click')
    await flushPromises()
    const codes = () => Array.from(document.body.querySelectorAll<HTMLElement>('[data-test="select-list"] [role="option"]')).map((o) => o.dataset.value)
    expect(codes()).toEqual(['M01', 'M01-S01-T03'])
    const input = document.body.querySelector<HTMLInputElement>('[data-test="code-picker-search"]')!
    input.value = 'loader'; input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    expect(codes()).toEqual(['M01-S01-T03'])
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(document.body.querySelector('[data-test="select-list"]')).toBeNull()
    expect(wrapper.find('[data-picked="M01-S01-T03"]').exists()).toBe(true)
    await wrapper.get('[data-test="unpick-M01-S01-T01"]').trigger('click')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ depends_on: ['M01-S01-T03'] }])
    wrapper.unmount()
  })

  it('offers no source or target parameter', () => {
    const wrapper = addForm()
    for (const key of ['source', 'target']) {
      expect(wrapper.find(`[data-parameter="${key}"]`).exists()).toBe(false)
    }
  })

  it('suggests the next free code and previews the full id of a new task', async () => {
    const wrapper = addForm({ taskIds: ['M01-S01-T01', 'M01-S01-T04', 'M02-S01-T09'] })
    const field = wrapper.find('[data-test="id"]')
    expect(wrapper.text()).toContain('Kód (volitelné)')
    expect(field.attributes('placeholder')).toBe('T05')
    expect(wrapper.find('[data-test="id-preview"]').text()).toBe('Id: M01-S01-T05')
    await field.setValue('T07')
    expect(wrapper.find('[data-test="id-preview"]').text()).toBe('Id: M01-S01-T07')
    await field.setValue('T-7')
    expect(wrapper.find('[data-test="id-invalid"]').exists()).toBe(true)
    await wrapper.find('[data-test="title"]').setValue('X')
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
  })

  it('sends the workflow, short code and body of a new task', async () => {
    const wrapper = addForm()
    await wrapper.find('[data-test="title"]').setValue('X')
    await wrapper.find('[data-test="id"]').setValue('M01-S01-T09')
    await chooseOption(wrapper, '[data-test="workflow"]', 'plan')
    await wrapper.find('[data-test="body"]').setValue('Text')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([
      { step: 'M01-S01', title: 'X', id: 'T09', workflow: 'plan', body: 'Text' },
    ])
  })

  it('sends only changed fields when editing', async () => {
    const wrapper = editForm()
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="title"]').setValue('Loader 2')
    await chooseOption(wrapper, '[data-test="workflow"]', 'custom-flow')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([{ title: 'Loader 2', workflow: 'custom-flow' }])
  })

  it('clears an own workflow and writes when switched to inherited', async () => {
    const wrapper = editForm({ own_workflow: 'plan', own_writes: ['src/'] })
    await chooseOption(wrapper, '[data-test="workflow"]', '')
    await wrapper.find('[data-test="inherit-writes"]').setValue(true)
    await chooseOption(wrapper, '[data-test="status"]', 'cancelled')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([
      { status: 'cancelled', clear_workflow: true, clear_writes: true },
    ])
  })

  it('switches auto-merge of the task off, on or back to inherited', async () => {
    const off = editForm()
    await chooseOption(off, '[data-test="auto-merge"]', 'off')
    await off.find('form').trigger('submit')
    expect(off.emitted('submit')?.[0]).toEqual([{ auto_merge: false }])

    const inherit = editForm({ own_auto_merge: false })
    await chooseOption(inherit, '[data-test="auto-merge"]', 'inherit')
    await inherit.find('form').trigger('submit')
    expect(inherit.emitted('submit')?.[0]).toEqual([{ clear_auto_merge: true }])

    const on = editForm({ own_auto_merge: false })
    await chooseOption(on, '[data-test="auto-merge"]', 'on')
    await on.find('form').trigger('submit')
    expect(on.emitted('submit')?.[0]).toEqual([{ auto_merge: true }])
  })

  it('disables the status of a done task', () => {
    const wrapper = editForm({ status: 'done', board_state: 'done' })
    expect(wrapper.find('[data-test="status"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="done-note"]').exists()).toBe(true)
  })

  it('preselects the step of the context, else the first one', () => {
    const preset = mount(TaskForm, {
      props: { mode: 'add', steps: data.steps, workflows: data.workflows, busy: false, error: null, initialStep: 'M02-S01' },
    })
    expect(preset.get('[data-test="step"]').text()).toContain('M02-S01')
    const unknown = mount(TaskForm, {
      props: { mode: 'add', steps: data.steps, workflows: data.workflows, busy: false, error: null, initialStep: 'NOPE' },
    })
    expect(unknown.get('[data-test="step"]').text()).toContain('M01-S01')
  })

  it('explains how to create a step when there is none', () => {
    window.location.hash = '#/r/haifa/backlog/new'
    const wrapper = mount(TaskForm, {
      props: { mode: 'add', steps: [], workflows: data.workflows, busy: false, error: null },
    })
    expect(wrapper.find('[data-test="step"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="no-steps"]').text()).toContain('zatím žádný není')
    expect(wrapper.get('[data-test="no-steps-link"]').attributes('href')).toBe('#/r/haifa/backlog/new-step')
    expect(wrapper.get('[data-test="no-steps-link"]').text()).toBe('Založit step')
  })

  it('puts Vylepšit agentem at the top and says why it waits', async () => {
    const wrapper = addForm()
    const improve = wrapper.get('[data-test="improve"]')
    const title = wrapper.get('[data-test="title"]').element
    expect(improve.element.compareDocumentPosition(title) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(improve.attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="advice-blocker"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="workflow-advice"] button').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="title"]').setValue('Nový')
    expect(wrapper.get('[data-test="improve"]').attributes('disabled')).toBeUndefined()
  })

  it('keeps the rarely used fields in a collapsed Další nastavení', () => {
    const fresh = addForm()
    const details = fresh.get('details[data-test="advanced"]')
    expect(details.attributes('open')).toBeUndefined()
    for (const field of ['writes', 'depends', 'related', 'task-parameters']) {
      expect(details.find(`[data-test="${field}"]`).exists()).toBe(true)
    }
    const plain = editForm({ own_writes: [], depends_on: [], related: [], own_auto_merge: null })
    expect(plain.get('details[data-test="advanced"]').attributes('open')).toBeUndefined()
    const custom = editForm({ own_writes: ['src/'] })
    expect(custom.get('details[data-test="advanced"]').attributes('open')).toBeDefined()
  })

  it('applies the agent proposal at once, locks the fields while it runs and opens Další nastavení', async () => {
    const proposal = {
      title: 'Improved task', body: 'Acceptance criteria', writes: ['src/'],
      depends_on: ['M01-S01-T01'], related: [], workflow: 'plan', reason: 'Clear scope',
      parameters: { test_timeout: 120 }, usage: { tokens: 5, cost_usd: 0.01 },
    }
    api.postApi.mockResolvedValue({ job_id: 'improve-job' })
    api.getApi.mockResolvedValue({ state: 'running', recommendation: null })
    vi.useFakeTimers()
    const wrapper = addForm({ initialTitle: 'Original' })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(api.postApi.mock.calls[0]?.[1]).not.toHaveProperty('harness')
    expect(wrapper.get('fieldset[data-test="fields"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
    api.getApi.mockImplementation(async (url: string) => url.startsWith('/backlog/task-advice/')
      ? { state: 'succeeded', recommendation: proposal }
      : { state: 'succeeded', recommendation: { decision: 'existing', workflow_name: 'plan', workflow_yaml: null, reason: 'Plan fits', outline: [] } })
    await vi.advanceTimersByTimeAsync(1000)
    await flushPromises()
    vi.useRealTimers()
    expect(wrapper.get('fieldset[data-test="fields"]').attributes('disabled')).toBeUndefined()
    expect((wrapper.get('[data-test="title"]').element as HTMLInputElement).value).toBe('Improved task')
    expect((wrapper.get('[data-test="body"]').element as HTMLTextAreaElement).value).toBe('Acceptance criteria')
    expect(wrapper.get('details[data-test="advanced"]').attributes('open')).toBeDefined()
    expect(wrapper.get('[data-test="improve-note"]').text()).toContain('Clear scope')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      step: 'M01-S01', title: 'Improved task', body: 'Acceptance criteria', writes: ['src/'],
      depends_on: ['M01-S01-T01'], workflow: 'plan', parameters: { test_timeout: 120 },
    })
    wrapper.unmount()
  })

  it('proposes the workflow from the improved draft and saves a new one by its reference', async () => {
    const proposal = {
      title: 'Improved task', body: 'Acceptance criteria', writes: null, depends_on: [], related: [],
      workflow: 'plan', reason: 'Clear scope', usage: null,
    }
    const recommendation = {
      decision: 'new', workflow_name: 'research-x', workflow_yaml: 'name: research-x\nsteps: []',
      reason: 'Analysis only', outline: [{ name: 'research' }],
    }
    api.postApi.mockImplementation(async (url: string) => ({ job_id: url === '/backlog/task-advice' ? 'improve-job' : 'advice-job' }))
    api.getApi.mockImplementation(async (url: string) => ({
      state: 'succeeded', recommendation: url.startsWith('/backlog/task-advice/') ? proposal : recommendation,
    }))
    const wrapper = addForm({ initialTitle: 'Original' })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(api.postApi.mock.calls.map((call) => call[0])).toEqual(['/backlog/task-advice', '/backlog/workflow-advice'])
    expect(api.postApi.mock.calls[1]?.[1]).toMatchObject({ draft: { title: 'Improved task', body: 'Acceptance criteria', workflow: 'plan' } })
    const result = wrapper.get('[data-test="advice-result"]')
    expect(result.text()).toContain('research-x')
    expect(result.text()).toContain('nové workflow')
    expect(result.text()).toContain('Analysis only')
    expect(result.get('pre').text()).toContain('name: research-x')
    expect(await selectLabels(wrapper, '[data-test="workflow"]')).toContain('research-x')
    expect(wrapper.get('[data-test="improve-note"]').text()).toContain('Clear scope')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      title: 'Improved task', workflow: 'research-x', workflow_advice_id: 'advice-job',
    })
    wrapper.unmount()
  })

  it('keeps the improvement when the workflow proposal fails', async () => {
    const proposal = {
      title: 'Improved task', body: 'Acceptance criteria', writes: null, depends_on: [], related: [],
      workflow: 'plan', reason: 'Clear scope', usage: null,
    }
    api.postApi.mockImplementation(async (url: string) => ({ job_id: url === '/backlog/task-advice' ? 'improve-job' : 'advice-job' }))
    api.getApi.mockImplementation(async (url: string) => url.startsWith('/backlog/task-advice/')
      ? { state: 'succeeded', recommendation: proposal }
      : { state: 'failed', recommendation: null, error: 'Workflow agent selhal.' })
    const wrapper = addForm({ initialTitle: 'Original' })
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-test="title"]').element as HTMLInputElement).value).toBe('Improved task')
    expect((wrapper.get('[data-test="body"]').element as HTMLTextAreaElement).value).toBe('Acceptance criteria')
    expect(wrapper.get('[data-test="workflow-advice"] [role="alert"]').text()).toBe('Workflow agent selhal.')
    expect(wrapper.find('[data-test="advice-result"]').exists()).toBe(false)
    const adviceButton = wrapper.get('[data-test="workflow-advice"] button')
    expect(adviceButton.attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit')
    const input = wrapper.emitted('submit')?.[0]?.[0] as Record<string, unknown>
    expect(input).toMatchObject({ title: 'Improved task', workflow: 'plan' })
    expect(input).not.toHaveProperty('workflow_advice_id')
    wrapper.unmount()
  })

  it('starts the agent on mount with autoImprove', async () => {
    api.getApi.mockResolvedValue({ state: 'running', recommendation: null })
    vi.useFakeTimers()
    const wrapper = mount(TaskForm, { props: {
      mode: 'edit', steps: [], workflows: data.workflows, task: taskNode(), taskBody: 'Body',
      busy: false, error: null, autoImprove: true,
    } })
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/task-advice', expect.objectContaining({ task_id: taskNode().id }), expect.any(AbortSignal))
    expect(wrapper.get('[data-test="improve"]').attributes('aria-busy')).toBe('true')
    wrapper.unmount()
    vi.useRealTimers()
  })

  it('sends a chosen thinking level', async () => {
    const wrapper = addForm()
    await wrapper.get('[data-test="title"]').setValue('Nový')
    await chooseOption(wrapper, '[data-test="parameter-thinking"]', 'high')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({ parameters: { thinking: 'high' } })
  })

  it('offers the parameters without an AI proposal, with Czech labels', async () => {
    const wrapper = addForm()
    const params = wrapper.get('[data-test="task-parameters"]')
    expect(params.find('[data-parameter="test"]').exists()).toBe(false)
    expect(params.get('[data-parameter="test_timeout"]').text()).toContain('Limit testů (s)')
    expect(params.find('[data-parameter="specs_dir"]').exists()).toBe(false)
    expect(params.find('[data-parameter="auto_merge"]').exists()).toBe(true)
    await wrapper.get('[data-test="title"]').setValue('Nový')
    await wrapper.get('[data-test="parameter-test_timeout"]').setValue('300')
    await chooseOption(wrapper, '[data-test="parameter-auto_continue"]', 'false')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toMatchObject({
      parameters: { test_timeout: 300, auto_continue: false },
    })
  })

  it('shows the own parameters of an edited task and sends only a changed one', async () => {
    const wrapper = editForm({ own_parameters: { test_timeout: 120 } })
    expect((wrapper.get('[data-test="parameter-test_timeout"]').element as HTMLInputElement).value).toBe('120')
    expect(wrapper.get('[data-test="save"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="parameter-test_timeout"]').setValue('600')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]?.[0]).toEqual({ parameters: { test_timeout: 600, auto_merge: null } })
  })

  it('names the statuses in Czech', async () => {
    const wrapper = editForm()
    expect(wrapper.get('[data-test="status"]').text()).toContain('K řešení')
    const done = editForm({ status: 'done', board_state: 'done' })
    expect(done.get('[data-test="status"]').text()).toContain('Hotovo')
  })

  it('shows the write error with its issues', () => {
    const wrapper = mount(TaskForm, {
      props: {
        mode: 'add',
        steps: data.steps,
        workflows: [],
        busy: false,
        error: {
          message: 'change rejected',
          issues: [{ code: 'unknown_ref', message: 'unknown NOPE', path: 'backlog/x.md', id: null }],
        },
      },
    })
    const error = wrapper.find('[data-test="write-error"]')
    expect(error.text()).toContain('change rejected')
    expect(error.find('[data-issue="unknown_ref"]').text()).toContain('unknown NOPE')
  })

  it('reports unsaved changes until the form is submitted', async () => {
    const wrapper = addForm()
    expect(hasUnsavedChanges()).toBe(false)
    await wrapper.find('[data-test="title"]').setValue('Rozepsaný')
    expect(hasUnsavedChanges()).toBe(true)
    await wrapper.find('form').trigger('submit')
    expect(hasUnsavedChanges()).toBe(false)
    await wrapper.setProps({ error: { message: 'change rejected', issues: [] } })
    expect(hasUnsavedChanges()).toBe(true)
    wrapper.unmount()
    expect(hasUnsavedChanges()).toBe(false)
  })

  it('asks before Zrušit drops the changes', async () => {
    const wrapper = addForm()
    await wrapper.find('[data-test="cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    await wrapper.find('[data-test="title"]').setValue('Rozepsaný')
    await wrapper.find('[data-test="cancel"]').trigger('click')
    expect(leaveDialog.open).toBe(true)
    expect(wrapper.emitted('cancel')).toHaveLength(1)
    confirmLeave()
    await flushPromises()
    expect(wrapper.emitted('cancel')).toHaveLength(2)
    wrapper.unmount()
  })
})
