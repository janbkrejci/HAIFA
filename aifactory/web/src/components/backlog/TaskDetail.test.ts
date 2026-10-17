import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import TaskDetail from './TaskDetail.vue'
import TaskForm from './TaskForm.vue'
import { runCheck, taskDetail } from '@/test/backlogFixtures'
import { answerDialog, openDialog } from '@/test/modal'
import { resetNamesForTests, setNames } from '@/lib/names'

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
  it('shows the task documents card, loaded by the task id', async () => {
    api.getApi.mockReset().mockResolvedValue({ task_id: 'x', documents: [] })
    const wrapper = detailWrapper()
    await flushPromises()
    expect(wrapper.find('[data-test="task-documents"]').exists()).toBe(true)
    expect(api.getApi).toHaveBeenCalledWith(`/backlog/tasks/${taskDetail().task.id}/documents`)
    wrapper.unmount()
  })

  it('opens shared advice editing with stored body and relationships and forwards the save reference', async () => {
    api.postApi.mockResolvedValue({ job_id: 'detail-job' })
    api.getApi.mockResolvedValue({ state: 'succeeded', recommendation: {
      decision: 'existing', workflow_name: 'plan', workflow_yaml: null,
      reason: 'Analysis first', outline: [{ name: 'plan' }],
    } })
    const wrapper = detailWrapper()
    await wrapper.get('[data-test="edit"]').trigger('click')
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

  it.each(['cancelled', 'running', 'in review', 'awaiting merge'] as const)('disables Vylepšit agentem for %s tasks', (state) => {
    const detail = taskDetail()
    detail.task.board_state = state
    const wrapper = mount(TaskDetail, { props: { detail, workflows: ['plan'], busy: false, error: null } })
    expect(wrapper.get('[data-test="improve"]').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })

  it('Vylepšit agentem opens the edit form and starts the agent there', async () => {
    api.postApi.mockReset().mockResolvedValue({ job_id: 'improve-job' })
    api.getApi.mockReset().mockResolvedValue({ state: 'running', recommendation: null })
    const wrapper = detailWrapper()
    const button = wrapper.get('[data-test="improve"]')
    expect(button.text()).toContain('Vylepšit agentem')
    expect(button.attributes('disabled')).toBeUndefined()
    await button.trigger('click')
    await flushPromises()
    const form = wrapper.findComponent(TaskForm)
    expect(form.exists()).toBe(true)
    expect(form.props('autoImprove')).toBe(true)
    expect(api.postApi).toHaveBeenCalledWith('/backlog/task-advice', expect.objectContaining({ task_id: 'M01-S01-T02' }), expect.any(AbortSignal))
    expect(api.postApi.mock.calls[0][1]).not.toHaveProperty('harness')
    // one improve button on the page: the form's
    expect(wrapper.findAll('[data-test="improve"]')).toHaveLength(1)
    expect(form.find('[data-test="improve"]').exists()).toBe(true)
    await wrapper.get('[data-test="cancel"]').trigger('click')
    await wrapper.get('[data-test="edit"]').trigger('click')
    expect(wrapper.findComponent(TaskForm).props('autoImprove')).toBe(false)
    wrapper.unmount()
  })

  it('Vylepšit agentem fills the improved task and the proposed workflow for saving', async () => {
    const proposal = {
      title: 'Improved task', body: 'Acceptance criteria', writes: null, depends_on: [], related: [],
      workflow: null, reason: 'Clear scope', usage: null,
    }
    const recommendation = {
      decision: 'new', workflow_name: 'research-x', workflow_yaml: 'name: research-x', reason: 'Analysis only', outline: [],
    }
    api.postApi.mockReset().mockImplementation(async (url: string) => ({ job_id: url === '/backlog/task-advice' ? 'improve-job' : 'advice-job' }))
    api.getApi.mockReset().mockImplementation(async (url: string) => {
      if (url.startsWith('/backlog/task-advice/')) return { state: 'succeeded', recommendation: proposal }
      if (url.startsWith('/backlog/workflow-advice/')) return { state: 'succeeded', recommendation }
      return { task_id: 'x', documents: [] }
    })
    const wrapper = detailWrapper()
    await wrapper.get('[data-test="improve"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="advice-result"]').text()).toContain('Analysis only')
    expect(wrapper.get('[data-test="improve-note"]').text()).toContain('Clear scope')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.emitted('edit')?.[0]?.[0]).toMatchObject({
      title: 'Improved task', workflow: 'research-x', workflow_advice_id: 'advice-job',
    })
    wrapper.unmount()
  })

  it('has no workflow or link inputs in the read-only view', () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('input').exists()).toBe(false)
    expect(wrapper.find('[data-test="workflow-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="assign"]').exists()).toBe(false)
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

  it('offers to continue the newest run when it failed or stopped', async () => {
    const base = taskDetail()
    const run = base.runs[0]!
    const older = { ...run, run_id: 'r-0', state: 'failed' }
    const stopped = taskDetail({ runs: [{ ...run, state: 'stopped' }, older] })
    api.postApi.mockResolvedValue({ task_id: run.task_id, action: 'retry', run: null, pending: true })
    const wrapper = mount(TaskDetail, { props: { detail: stopped, workflows: [], busy: false, error: null } })
    expect(wrapper.find('[data-run="r-0"] [data-test="retry-run"]').exists()).toBe(false)
    await wrapper.get('[data-run="r-1"] [data-test="retry-run"]').trigger('click')
    await wrapper.get('[data-test="retry-form"]').trigger('submit')
    await flushPromises()
    expect(api.postApi).toHaveBeenLastCalledWith('/runs/r-1/retry', {})
    expect(wrapper.emitted('retried')).toHaveLength(1)
    const succeeded = mount(TaskDetail, { props: { detail: base, workflows: [], busy: false, error: null } })
    expect(succeeded.find('[data-test="retry-run"]').exists()).toBe(false)
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

  it.each(['done', 'cancelled', 'running', 'in review', 'awaiting merge'] as const)('offers no cancel for %s tasks', (state) => {
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
    await wrapper.find('[data-test="unrelate-M02-S01-T01"]').trigger('click')
    expect(wrapper.emitted('link')).toEqual([
      [{ depends_on: ['M01-S01-T01'], remove: true }],
      [{ related: ['M02-S01-T01'], remove: true }],
    ])
  })

  it('shows each writes path as a chip that shows the full path and wraps', () => {
    const detail = taskDetail()
    const long = 'aifactory/src/aifactory/some/really/long/path/without/any/spaces/at/all/file_name.py'
    detail.task.writes = [long]
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    const chip = wrapper.get('[data-test="writes"] .chip')
    expect(chip.text()).toBe(long)
    expect(chip.attributes('title')).toBeUndefined()
    wrapper.unmount()
  })

  it('opens the blocking-task search dialog from the edit form', async () => {
    setNames({ names: { 'M02-S01-T09': { title: 'Filtr', level: 'task' } } })
    const wrapper = mount(TaskDetail, {
      props: { detail: taskDetail(), workflows: [], busy: false, error: null }, attachTo: document.body,
    })
    await wrapper.get('[data-test="edit"]').trigger('click')
    await wrapper.get('[data-test="depends"]').trigger('click')
    await flushPromises()
    expect(document.body.querySelector('[data-test="code-picker-search"]')).not.toBeNull()
    wrapper.unmount()
    resetNamesForTests()
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
  it('says the task is ready to run when nothing stops it', () => {
    const wrapper = detailWrapper()
    const banner = wrapper.get('[data-test="run-readiness"]')
    expect(banner.attributes('data-tone')).toBe('ok')
    expect(banner.text()).toContain('Připraveno ke spuštění')
    expect(banner.text()).toContain('plan-build')
    expect(banner.findAll('[data-test="readiness-reason"]')).toHaveLength(0)
  })

  it('lists what stops a task without a workflow', () => {
    const detail = taskDetail()
    detail.task = { ...detail.task, workflow: null }
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    const banner = wrapper.get('[data-test="run-readiness"]')
    expect(banner.attributes('data-tone')).toBe('warn')
    expect(banner.findAll('[data-test="readiness-reason"]').map((r) => r.text())).toEqual([
      'Task nemá workflow – nastav ho na tasku, stepu nebo projektu.',
    ])
  })

  it('lists every unmet dependency of a blocked task', () => {
    const detail = taskDetail()
    detail.task = {
      ...detail.task,
      board_state: 'blocked',
      blocked_by: [
        { id: 'M01-S01', reason: 'incomplete', missing: ['M01-S01-T01'] },
        { id: 'M01-S01-T05', reason: 'not_done', missing: [] },
      ],
    }
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    const banner = wrapper.get('[data-test="run-readiness"]')
    expect(banner.attributes('data-tone')).toBe('warn')
    const reasons = banner.findAll('[data-test="readiness-reason"]')
    expect(reasons).toHaveLength(2)
    expect(reasons[0].text()).toContain('M01-S01 – step má nehotové tasky: M01-S01-T01')
  })

  it('a done task offers Navázat follow-upem instead of Spustit, Upravit and Vylepšit agentem', () => {
    const detail = taskDetail()
    detail.task = { ...detail.task, board_state: 'done' }
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    expect(wrapper.find('[data-test="run"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="edit"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="improve"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="auto-queue"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="follow-up"]').text()).toContain('Navázat follow-upem')
    wrapper.unmount()
  })

  it('a task that is not done has no follow-up button', () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('[data-test="follow-up"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="run"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('creates a follow-up task from the dialog and forwards the result', async () => {
    const detail = taskDetail()
    detail.task = { ...detail.task, board_state: 'done' }
    const result = { action: 'follow-up', changed: true, path: 'x.md', task: { ...detail.task, id: 'M01-S01-T09' }, issues: [], commit: null, run: null, pending: true }
    api.postApi.mockReset().mockResolvedValue(result)
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    expect(wrapper.find('[data-test="follow-up-dialog"]').exists()).toBe(false)
    await wrapper.get('[data-test="follow-up"]').trigger('click')
    expect(wrapper.find('[data-test="follow-up-dialog"]').exists()).toBe(true)
    await wrapper.get('[data-test="follow-up-body"]').setValue('Přidat export.')
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/tasks/M01-S01-T02/follow-up', { body: 'Přidat export.', run: true })
    expect(wrapper.emitted('follow-up')).toEqual([[result]])
    expect(wrapper.find('[data-test="follow-up-dialog"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('links the followed task and lists the tasks that follow this one', () => {
    const detail = taskDetail()
    detail.follows = { id: 'M01-S01-T01', kind: 'task', title: 'Původní', state: 'done' }
    detail.followed_by = [{ id: 'M01-S01-T07', title: 'Dál', board_state: 'todo' }]
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    const follows = wrapper.get('[data-test="follows"]')
    expect(follows.text()).toContain('Navazuje na M01-S01-T01')
    expect(follows.get('a').attributes('href')).toContain('M01-S01-T01')
    const followers = wrapper.get('[data-test="followed-by"]')
    expect(followers.text()).toContain('M01-S01-T07')
    expect(followers.get('a').attributes('href')).toContain('M01-S01-T07')
    wrapper.unmount()
  })

  it('shows no follow links without them', () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('[data-test="follows"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="followed-by"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('mutes the banner for a done task', () => {
    const detail = taskDetail()
    detail.task = { ...detail.task, board_state: 'done' }
    const wrapper = mount(TaskDetail, { props: { detail, workflows: [], busy: false, error: null } })
    const banner = wrapper.get('[data-test="run-readiness"]')
    expect(banner.attributes('data-tone')).toBe('muted')
    expect(banner.text()).toContain('Task je hotový, znovu se nespouští.')
  })

  it('replaces the body and documents card with the edit form while editing', async () => {
    const wrapper = detailWrapper()
    expect(wrapper.find('[data-test="task-documents"] .mdview[data-test="body"]').exists()).toBe(true)
    await wrapper.get('[data-test="edit"]').trigger('click')
    expect(wrapper.find('.mdview').exists()).toBe(false)
    expect(wrapper.find('[data-test="task-documents"]').exists()).toBe(false)
    expect(wrapper.find('form').exists()).toBe(true)
  })
})
