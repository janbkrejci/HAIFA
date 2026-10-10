import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskDetail from './TaskDetail.vue'
import { runCheck, taskDetail } from '@/test/backlogFixtures'
import { chooseOption } from '@/test/select'
import { answerDialog, openDialog } from '@/test/modal'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', () => api)

afterEach(() => {
  document.body.innerHTML = ''
})

function detailWrapper(error: { message: string; issues: [] } | null = null) {
  return mount(TaskDetail, {
    props: { detail: taskDetail(), workflows: ['plan', 'plan-build'], busy: false, error },
  })
}

describe('TaskDetail', () => {
  it('opens shared advice editing with stored body and relationships and forwards the save reference', async () => {
    api.postApi.mockResolvedValue({ job_id: 'detail-job' })
    api.getApi.mockResolvedValue({ state: 'succeeded', recommendation: {
      decision: 'existing', workflow_name: 'plan', workflow_yaml: null,
      reason: 'Analysis first', outline: [{ name: 'plan' }],
    } })
    const wrapper = detailWrapper()
    const opener = wrapper.findAll('button').find((button) => button.text() === 'Upravit a navrhnout workflow')!
    await opener.trigger('click')
    await wrapper.get('[data-test="workflow-advice"] button').trigger('click')
    await flushPromises()
    const detail = taskDetail()
    expect(api.postApi.mock.calls.at(-1)?.[1]).toMatchObject({ task_id: detail.task.id, draft: {
      body: detail.body, depends_on: detail.task.depends_on, related: detail.task.related,
      workflow: null, writes: null,
    } })
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('edit')?.[0]).toEqual([{ workflow: 'plan', workflow_advice_id: 'detail-job' }])
    expect(detail.task.own_workflow).toBeNull()
    wrapper.unmount()
  })

  it.each(['done', 'cancelled', 'running', 'in review'] as const)('disables advice for %s tasks', (state) => {
    const detail = taskDetail()
    detail.task.board_state = state
    const wrapper = mount(TaskDetail, { props: { detail, workflows: ['plan'], busy: false, error: null } })
    const opener = wrapper.findAll('button').find((button) => button.text() === 'Upravit a navrhnout workflow')!
    expect(opener.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('shows the header, the body, both link directions, runs and PRs', () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('[data-test="task-id"]').text()).toBe('M01-S01-T02')
    expect(wrapper.find('[data-test="task-title"]').text()).toBe('Loader')
    expect(wrapper.find('[data-state]').text()).toBe('Připraveno')
    expect(wrapper.find('[data-test="owner"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Vlastník')
    expect(wrapper.find('[data-test="workflow"]').text()).toContain('(zděděno)')
    expect(wrapper.find('[data-test="body"]').text()).toContain('Načíst backlog.')
    const dep = wrapper.find('[data-dep="M01-S01-T01"]')
    expect(dep.text()).toContain('Schema')
    expect(dep.find('a').attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T01')
    const block = wrapper.find('[data-block="M01-S01-T03"]')
    expect(block.text()).toContain('Writer')
    expect(block.text()).toContain('Blokováno')
    expect(wrapper.find('[data-run="r-1"] a').attributes('href')).toBe('#/r/haifa/runs/r-1')
    const pr = wrapper.find('[data-pr="3"] a')
    expect(pr.attributes('href')).toBe('https://example.test/pr/3')
    expect(pr.attributes('target')).toBe('_blank')
    expect(pr.attributes('rel')).toBe('noopener')
  })

  it('shows empty runs and PRs', () => {
    const wrapper = mount(TaskDetail, {
      props: { detail: taskDetail({ runs: [], prs: [] }), workflows: [], busy: false, error: null },
    })
    expect(wrapper.find('[data-test="no-runs"]').text()).toBe('Žádné běhy')
    expect(wrapper.find('[data-test="no-prs"]').text()).toBe('Žádné PR')
  })

  it('labels the unlink buttons without a native tooltip', async () => {
    const wrapper = mount(TaskDetail, {
      props: { detail: taskDetail(), workflows: ['plan'], busy: false, error: null },
      attachTo: document.body,
    })
    const unlink = wrapper.find('[data-test="unlink-M01-S01-T01"]')
    expect(unlink.attributes('title')).toBeUndefined()
    expect(unlink.attributes('aria-label')).toBe('Odebrat vazbu')
    expect(wrapper.find('[title]').exists()).toBe(false)
    await unlink.trigger('focusin')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toContain('Odebrat vazbu')
    wrapper.unmount()
  })

  it('enables Spustit for a task with a workflow, without a tooltip', async () => {
    const wrapper = mount(TaskDetail, {
      props: { detail: taskDetail(), workflows: ['plan-build'], busy: false, error: null },
      attachTo: document.body,
    })
    const run = wrapper.find('[data-test="run"]')
    expect(run.attributes('disabled')).toBeUndefined()
    await run.trigger('focusin')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')).toBeNull()
    await run.trigger('click')
    expect(wrapper.emitted('open-run')).toHaveLength(1)
    wrapper.unmount()
  })

  it('disables Spustit for a task without a workflow and says why', async () => {
    const detail = taskDetail()
    detail.task = { ...detail.task, workflow: null }
    const wrapper = mount(TaskDetail, {
      props: { detail, workflows: ['plan-build'], busy: false, error: null },
      attachTo: document.body,
    })
    const run = wrapper.find('[data-test="run"]')
    expect(run.attributes('disabled')).toBeDefined()
    expect(run.attributes('title')).toBeUndefined()
    await run.trigger('click')
    expect(wrapper.emitted('open-run')).toBeUndefined()
    run.element.closest('[data-test="tip-anchor"]')!.dispatchEvent(new MouseEvent('mouseenter'))
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toBe(
      'Task nemá workflow – nastav ho na tasku, stepu nebo projektu.',
    )
    wrapper.unmount()
  })

  it.each([
    ['done', 'Task je hotový, znovu se nespouští.'],
    ['cancelled', 'Task je zrušený, nespouští se.'],
  ] as const)('disables Spustit for a %s task and says why', async (state, tip) => {
    const detail = taskDetail()
    detail.task = { ...detail.task, board_state: state }
    const wrapper = mount(TaskDetail, {
      props: { detail, workflows: ['plan-build'], busy: false, error: null },
      attachTo: document.body,
    })
    const run = wrapper.get('[data-test="run"]')
    expect(run.attributes('disabled')).toBeDefined()
    run.element.closest('[data-test="tip-anchor"]')!.dispatchEvent(new MouseEvent('mouseenter'))
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toBe(tip)
    // a finished task is no longer queued
    expect(wrapper.find('[data-test="auto-queue"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('shows whether auto continue takes the task and toggles it', async () => {
    const detail = taskDetail()
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    expect(wrapper.get('[data-test="auto-queue-state"]').text()).toBe('ve frontě')
    await wrapper.get('[data-test="auto-queue-toggle"]').trigger('click')
    expect(wrapper.emitted('exclude')).toEqual([['M01-S01-T02', true]])
    await wrapper.setProps({ detail: { ...detail, task: { ...detail.task, auto_excluded: true } } })
    expect(wrapper.get('[data-test="auto-queue-state"]').text()).toBe('odloženo')
    expect(wrapper.get('[data-test="auto-queue-toggle"]').text()).toContain('Vrátit do auto continue')
    await wrapper.get('[data-test="auto-queue-toggle"]').trigger('click')
    expect(wrapper.emitted('exclude')?.[1]).toEqual(['M01-S01-T02', false])
    await wrapper.setProps({ queueBusy: true })
    expect(wrapper.get('[data-test="auto-queue-toggle"]').attributes('disabled')).toBeDefined()
  })

  it('cancels a task that has not started after a confirmation', async () => {
    const wrapper = detailWrapper()
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    expect(openDialog()?.textContent).toContain('Zrušit task M01-S01-T02?')
    await answerDialog(false)
    expect(wrapper.emitted('cancel-task')).toBeUndefined()
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.emitted('cancel-task')).toEqual([[]])
    await wrapper.setProps({ busy: true })
    expect(wrapper.get('[data-test="cancel-task"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it.each(['done', 'cancelled', 'running', 'in review'] as const)('offers no cancel for %s tasks', (state) => {
    const detail = taskDetail()
    detail.task.board_state = state
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    expect(wrapper.find('[data-test="cancel-task"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('links every PR to Review and names its state in Czech', () => {
    const wrapper = detailWrapper()
    const pr = wrapper.get('[data-pr="3"]')
    expect(pr.get('[data-test="pr-state"]').text()).toBe('otevřený')
    expect(pr.get('[data-test="pr-review"]').attributes('href')).toBe('#/r/haifa/review/M01-S01-T02')
  })

  it('emits link changes', async () => {
    const wrapper = detailWrapper()
    await wrapper.find('[data-test="unlink-M01-S01-T01"]').trigger('click')
    await wrapper.find('[data-test="link-input"]').setValue('M02-S01-T01')
    await wrapper.find('[data-test="link-add"]').trigger('click')
    await wrapper.find('[data-test="unrelate-M02-S01-T01"]').trigger('click')
    expect(wrapper.emitted('link')).toEqual([
      [{ depends_on: ['M01-S01-T01'], remove: true }],
      [{ depends_on: ['M02-S01-T01'] }],
      [{ related: ['M02-S01-T01'], remove: true }],
    ])
  })

  it('assigns or clears the workflow', async () => {
    const wrapper = detailWrapper()
    await chooseOption(wrapper, '[data-test="workflow-select"]', 'plan')
    await wrapper.find('[data-test="assign"]').trigger('click')
    await chooseOption(wrapper, '[data-test="workflow-select"]', '')
    await wrapper.find('[data-test="assign"]').trigger('click')
    expect(wrapper.emitted('assign-workflow')).toEqual([['plan'], [null]])
  })

  it('opens the edit form and emits edit', async () => {
    const wrapper = detailWrapper()
    await wrapper.find('[data-test="edit"]').trigger('click')
    await wrapper.find('[data-test="title"]').setValue('Nový název')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.emitted('edit')?.[0]).toEqual([{ title: 'Nový název' }])
  })

  it('keeps the edit form open on a live refresh of the same task', async () => {
    const wrapper = detailWrapper()
    await wrapper.find('[data-test="edit"]').trigger('click')
    await wrapper.find('[data-test="title"]').setValue('Rozepsáno')
    await wrapper.setProps({ detail: taskDetail() })
    expect(wrapper.find('form').exists()).toBe(true)
    expect((wrapper.find('[data-test="title"]').element as HTMLInputElement).value).toBe(
      'Rozepsáno',
    )
    await wrapper.find('form').trigger('submit')
    await wrapper.setProps({ detail: taskDetail() })
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('closes the edit form when another task opens', async () => {
    const wrapper = detailWrapper()
    await wrapper.find('[data-test="edit"]').trigger('click')
    const other = taskDetail()
    await wrapper.setProps({ detail: { ...other, task: { ...other.task, id: 'M01-S01-T09' } } })
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('shows a write error', () => {
    const wrapper = detailWrapper({ message: 'change rejected', issues: [] })
    expect(wrapper.find('[data-test="write-error"]').text()).toContain('change rejected')
  })
  it('opens the run panel and forwards its events', async () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('[data-test="run-dialog"]').exists()).toBe(false)
    await wrapper.find('[data-test="run"]').trigger('click')
    expect(wrapper.emitted('open-run')).toHaveLength(1)
    await wrapper.setProps({
      run: {
        open: true,
        check: runCheck(),
        loading: false,
        busy: false,
        error: null,
        result: null,
        action: null,
        waiting: false,
      },
    })
    expect(wrapper.find('[data-test="run"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="run-start"]').trigger('click')
    await wrapper.find('[data-test="run-cancel"]').trigger('click')
    expect(wrapper.emitted('run-start')).toEqual([[{ force: false }]])
    expect(wrapper.emitted('run-cancel')).toHaveLength(1)
  })

  it('explains a blocked task in the header with a tooltip', async () => {
    const detail = taskDetail()
    detail.task = {
      ...detail.task,
      board_state: 'blocked',
      blocked_by: [{ id: 'M01-S01', reason: 'incomplete', missing: ['M01-S01-T01'] }],
    }
    const wrapper = mount(TaskDetail, {
      props: { detail, workflows: ['plan', 'plan-build'], busy: false, error: null },
      attachTo: document.body,
    })
    const chip = wrapper.find('[data-test="blocked-chip"]')
    expect(chip.text()).toBe('Blokováno')
    await chip.trigger('focusin')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent).toContain('M01-S01 – step má nehotové tasky: M01-S01-T01')
    wrapper.unmount()
  })
})
