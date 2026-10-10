import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskForm from './TaskForm.vue'
import { backlogData, taskNode } from '@/test/backlogFixtures'
import { chooseOption } from '@/test/select'

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
})

const data = backlogData()

function addForm() {
  return mount(TaskForm, {
    props: { mode: 'add', steps: data.steps, workflows: data.workflows, busy: false, error: null },
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
    const wrapper = addForm()
    await chooseOption(wrapper, '[data-test="step"]', 'M02-S01')
    await wrapper.find('[data-test="title"]').setValue(' Filtr ')
    await wrapper.find('[data-test="writes"]').setValue('web/src/\n\nweb/test/\n')
    await wrapper.find('[data-test="depends"]').setValue('M01-S01-T01, M01-S01-T02')
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

  it('sends the workflow, id and body of a new task', async () => {
    const wrapper = addForm()
    await wrapper.find('[data-test="title"]').setValue('X')
    await wrapper.find('[data-test="id"]').setValue('M01-S01-T09')
    await chooseOption(wrapper, '[data-test="workflow"]', 'plan')
    await wrapper.find('[data-test="body"]').setValue('Text')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('submit')?.[0]).toEqual([
      { step: 'M01-S01', title: 'X', id: 'M01-S01-T09', workflow: 'plan', body: 'Text' },
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

  it('puts the task text before the AI buttons and says why they wait', async () => {
    const wrapper = addForm()
    const body = wrapper.get('[data-test="body"]').element
    const advice = wrapper.get('[data-test="task-advice"]').element
    expect(body.compareDocumentPosition(advice) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(wrapper.get('[data-test="advice-blocker"]').text()).toContain('Vyplň titulek.')
    expect(wrapper.get('[data-test="workflow-advice"] button').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="title"]').setValue('Nový')
    expect(wrapper.find('[data-test="advice-blocker"]').exists()).toBe(false)
  })

  it('offers the parameters without an AI proposal, with Czech labels', async () => {
    const wrapper = addForm()
    const params = wrapper.get('[data-test="task-parameters"]')
    expect(params.find('[data-parameter="test"]').exists()).toBe(false)
    expect(params.get('[data-parameter="test_timeout"]').text()).toContain('Limit testů (s)')
    expect(params.get('[data-parameter="specs_dir"]').text()).toContain('Adresář specifikací')
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
    const wrapper = editForm({ own_parameters: { test_timeout: 120, specs_dir: 'specs/x' } })
    expect((wrapper.get('[data-test="parameter-test_timeout"]').element as HTMLInputElement).value).toBe('120')
    expect((wrapper.get('[data-test="parameter-specs_dir"]').element as HTMLInputElement).value).toBe('specs/x')
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
})
