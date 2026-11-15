import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import BacklogView from './BacklogView.vue'
import TaskForm from '@/components/backlog/TaskForm.vue'
import ContainerForm from '@/components/backlog/ContainerForm.vue'
import ContainerSettings from '@/components/backlog/ContainerSettings.vue'
import IntentDialog from '@/components/backlog/IntentDialog.vue'
import FollowUpDialog from '@/components/backlog/FollowUpDialog.vue'
import RunDialog from '@/components/backlog/RunDialog.vue'
import TaskDocuments from '@/components/backlog/TaskDocuments.vue'
import AutoContinueToggle from '@/components/backlog/AutoContinueToggle.vue'
import IssueList from '@/components/backlog/IssueList.vue'
import WorkflowAdvice from '@/components/backlog/WorkflowAdvice.vue'
import ImproveButton from '@/components/backlog/ImproveButton.vue'
import { ApiError } from '@/lib/api'
import { setLocale, t } from '@/lib/i18n'
import { cs, en, validateCatalogs } from '@/lib/i18n/catalogs'
import { intentProgressText } from '@/lib/backlogMessages'
import { resetTreeForTests, STATE_LABELS, COLUMN_LABELS, unmetLine } from '@/lib/backlog'
import { backlogData, containerDetail, expandTree, runCheck } from '@/test/backlogFixtures'
import { chooseOption, openSelect, optionLabels } from '@/test/select'
import { resetLiveForTests } from '@/lib/live'
import type { IntentJob } from '@/lib/intent'

enableAutoUnmount(afterEach)
function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}
async function language(value: 'en' | 'cs') {
  setLocale(value)
  await nextTick()
  await flushPromises()
}
beforeEach(() => {
  localStorage.clear()
  setLocale('en')
  resetTreeForTests()
  window.location.hash = '#/r/haifa/backlog'
  window.dispatchEvent(new HashChangeEvent('hashchange'))
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/containers/')) return ok(containerDetail())
    if (url.includes('/machine/harnesses')) return ok({ settings: { harnesses: {} }, models: {} })
    return ok(backlogData())
  }))
})
afterEach(() => {
  resetLiveForTests()
  vi.unstubAllGlobals()
  setLocale('en')
  document.body.innerHTML = ''
})

describe('Backlog locale without remounting', () => {
  it('keeps task and container drafts, validation and open advanced settings', async () => {
    expect(validateCatalogs(en, cs)).toEqual([])
    const form = mount(TaskForm, { props: { mode: 'add', steps: backlogData().steps, workflows: ['plan'], busy: false, error: null } })
    const container = mount(ContainerForm, { props: { level: 'project', busy: false, error: null } })
    await form.get('[data-test="title"]').setValue('Rozepsaný titulek')
    await form.get('[data-test="body"]').setValue('Keep **my** text')
    await form.get('[data-test="id"]').setValue('bad code!')
    const advanced = form.get('[data-test="advanced"]')
    ;(advanced.element as HTMLDetailsElement).open = true
    await advanced.trigger('toggle')
    await container.get('[data-test="container-title"]').setValue('Můj projekt')
    expect(form.get('[data-test="id-invalid"]').text()).toContain('The code may contain')
    await language('cs')
    expect(form.get('h2').text()).toBe('Nový task')
    expect(form.get('[data-test="id-invalid"]').text()).toContain('Kód smí obsahovat')
    expect((advanced.element as HTMLDetailsElement).open).toBe(true)
    expect((form.get('[data-test="title"]').element as HTMLInputElement).value).toBe('Rozepsaný titulek')
    expect((form.get('[data-test="body"]').element as HTMLTextAreaElement).value).toBe('Keep **my** text')
    expect((container.get('[data-test="container-title"]').element as HTMLInputElement).value).toBe('Můj projekt')
    await language('en')
    expect(form.get('h2').text()).toBe('New task')
    expect(form.get('[data-test="save"]').attributes('disabled')).toBeDefined()
  })

  it('keeps filters, tree expansion and an open settings panel', async () => {
    expandTree()
    const view = mount(BacklogView)
    await flushPromises()
    await chooseOption(view, '[data-test="project-filter"]', 'M01')
    const settings = view.get('[data-node="M01-S01"] [data-test="settings"]')
    await settings.trigger('click')
    await flushPromises()
    const panel = view.get('[data-test="settings-panel"]')
    await language('cs')
    expect(view.get('[data-test="project-filter"]').text()).toContain('M01')
    expect(view.get('[data-test="settings-panel"]').element).toBe(panel.element)
    expect(panel.text()).toContain('Nastavení')
    await view.get('[data-test="mode-kanban"]').trigger('click')
    expect(view.text()).toContain('Připraveno')
    await language('en')
    expect(view.get('[data-test="mode-kanban"]').classes()).toContain('active')
    expect(view.text()).toContain('Ready')
    expect(view.get('[data-test="project-filter"]').text()).toContain('M01')
  })

  it('keeps an Intent draft and edited proposal, refinement and task expansion', async () => {
    const proposal: NonNullable<IntentJob['proposal']> = {
      summary: 'Agentův návrh', applied: false, step: { id: 'P-S', title: 'Můj step', body: '', path: 'backlog/P/S', new: true },
      tasks: [{ id: 'P-S-T01', code: 'T01', title: 'Agentův titulek', body: 'Agentův text', workflow: 'plan', writes: ['src/'], depends_on: [], path: 'task.md' }],
      files: [], findings: [],
    }
    const job: IntentJob = { job_id: 'i1', state: 'ready', round: 1, intent: 'Záměr', target: {}, proposal, error: null, issues: [], notes: [], progress: [], applied: null }
    const fetch = vi.fn(async (_url: string, _init?: RequestInit) => ok(job))
    vi.stubGlobal('fetch', fetch)
    const dialog = mount(IntentDialog, { props: { pollMs: 60_000 } })
    await dialog.get('[data-test="intent-text"]').setValue('Můj rozepsaný záměr')
    await language('cs')
    expect((dialog.get('[data-test="intent-text"]').element as HTMLTextAreaElement).value).toBe('Můj rozepsaný záměr')
    await dialog.get('[data-test="intent-propose"]').trigger('click')
    await flushPromises()
    await dialog.get('[data-test="intent-task-edit"]').trigger('click')
    await dialog.get('[data-test="intent-task-title"]').setValue('Upravený titulek')
    await dialog.get('[data-test="intent-task-body"]').setValue('Upravené zadání')
    await dialog.get('[data-test="intent-note"]').setValue('Moje připomínka')
    const calls = fetch.mock.calls.length
    await language('en')
    expect(dialog.text()).toContain('New intent')
    expect(dialog.get('[data-test="intent-task"] details').attributes('open')).toBeDefined()
    expect((dialog.get('[data-test="intent-task-title"]').element as HTMLInputElement).value).toBe('Upravený titulek')
    expect((dialog.get('[data-test="intent-task-body"]').element as HTMLTextAreaElement).value).toBe('Upravené zadání')
    expect((dialog.get('[data-test="intent-note"]').element as HTMLTextAreaElement).value).toBe('Moje připomínka')
    expect(fetch).toHaveBeenCalledTimes(calls)
    await dialog.get('[data-test="intent-refine"]').trigger('click')
    const payload = JSON.parse((fetch.mock.calls.at(-1) as unknown as [string, RequestInit])[1].body as string)
    expect(payload).toMatchObject({ note: 'Moje připomínka', tasks: [{ code: 'T01', title: 'Upravený titulek', body: 'Upravené zadání' }] })
  })

  it('keeps follow-up drafts, run overrides and an open translated dropdown', async () => {
    const follow = mount(FollowUpDialog, { props: { taskId: 'T1', taskTitle: 'Původní zadání' } })
    await follow.get('[data-test="follow-up-body"]').setValue('Moje pokračování')
    await follow.get('[data-test="follow-up-title"]').setValue('Můj titulek')
    await follow.get('[data-test="follow-up-run"]').setValue(false)
    const run = mount(RunDialog, { props: { check: runCheck(), loading: false, busy: false, error: null, result: null } })
    await run.get('[data-test="run-note"]').setValue('My run note')
    await chooseOption(run, '[data-test="run-harness-name"]', 'codex')
    await openSelect(run, '[data-test="run-thinking"]')
    expect(optionLabels()).toContain('use roster')
    await language('cs')
    expect(optionLabels()).toContain('podle rosteru')
    expect((follow.get('[data-test="follow-up-body"]').element as HTMLTextAreaElement).value).toBe('Moje pokračování')
    expect((follow.get('[data-test="follow-up-title"]').element as HTMLInputElement).value).toBe('Můj titulek')
    expect((follow.get('[data-test="follow-up-run"]').element as HTMLInputElement).checked).toBe(false)
    expect((run.get('[data-test="run-note"]').element as HTMLTextAreaElement).value).toBe('My run note')
    expect(run.get('[data-test="run-harness-name"]').text()).toContain('codex')
  })

  it('keeps the selected document and container edits while translating labels', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ok({ documents: [{ kind: 'doc', label: 'Dokumentace', path: 'doc.md', exists: true, content: '# Původní obsah', problem: null }] })))
    const docs = mount(TaskDocuments, { props: { taskId: 'T1', body: 'Tělo zadání' } })
    await flushPromises()
    await docs.get('[data-test="doc-doc"]').trigger('click')
    expect(docs.get('[data-test="doc-doc"]').text()).toBe('Documentation')
    const settings = mount(ContainerSettings, { props: { container: containerDetail().container, workflows: ['plan'], busy: false, error: null } })
    await settings.get('[data-test="settings-title"]').setValue('Upravený kontejner')
    await language('cs')
    expect(docs.get('[data-test="doc-doc"]').attributes('aria-selected')).toBe('true')
    expect(docs.get('[data-test="doc-doc"]').text()).toBe('Dokumentace')
    expect(docs.get('[data-test="doc-content"]').text()).toContain('Původní obsah')
    expect((settings.get('[data-test="settings-title"]').element as HTMLInputElement).value).toBe('Upravený kontejner')
    expect(settings.get('[data-test="settings-save"]').text()).toBe('Uložit')
  })

  it('translates failures by code in place, preserving diagnostic codes and paths', async () => {
    const issue = { code: 'unknown_ref', message: 'Server prose', path: 'backlog/x.md', id: 'T1' }
    const error = mount(IssueList, { props: { code: 'invalid_value', message: 'Původní chyba serveru', issues: [issue] } })
    expect(error.get('.message').text()).toBe('An entered value is invalid.')
    expect(error.get('[data-test="error-details"]').text()).toContain('Původní chyba serveru')
    await language('cs')
    expect(error.text()).toContain('Zadaná hodnota není platná.')
    expect(error.text()).toContain('Odkazovaná položka neexistuje.')
    expect(error.text()).toContain('backlog/x.md')
    expect(error.get('[data-issue]').attributes('data-issue')).toBe('unknown_ref')
    vi.stubGlobal('fetch', vi.fn(async () => { throw new ApiError('trace_db_locked', 'Server prose') }))
    const view = mount(BacklogView)
    await flushPromises()
    expect(view.get('[data-test="retry"]').text()).toBe('Zkusit znovu')
    await language('en')
    expect(view.get('[data-test="error"]').text()).toContain('The run database is busy.')
    expect(view.get('[data-test="retry"]').text()).toBe('Try again')
  })

  it('keeps workflow advice and agent content while translating usage', async () => {
    const recommendation = { workflow_name: 'plan', decision: 'existing', reason: 'Důvod od agenta', workflow_yaml: null, outline: [] }
    vi.stubGlobal('fetch', vi.fn(async () => ok({ job_id: 'j1', state: 'succeeded', recommendation, usage: { tokens: 1234, cost_usd: 0.0105 } })))
    const wrapper = mount(WorkflowAdvice, { props: { draft: { title: 'User title' } } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="workflow-advice-cost"]').text()).toContain('$0.0105')
    expect(wrapper.get('[data-test="workflow-advice-cost"]').text()).toContain('1,234 tokens')
    await language('cs')
    expect(wrapper.get('[data-test="workflow-advice-cost"]').text()).toContain('0,0105')
    expect(wrapper.get('[data-test="workflow-advice-cost"]').text()).toContain('tokenů')
    expect(wrapper.get('[data-test="advice-result"]').text()).toContain('Důvod od agenta')
    expect(wrapper.get('[data-test="advice-result"]').text()).toContain('plan')
  })

  it.each(['workflow', 'task'])('translates a retained %s advice failure by code', async (kind) => {
    const code = kind === 'workflow' ? 'workflow_advice_failed' : 'task_advice_failed'
    vi.stubGlobal('fetch', vi.fn(async () => ok({ job_id: 'j1', state: 'failed', error_code: code, error: 'Původní chyba agenta' })))
    const wrapper = kind === 'workflow'
      ? mount(WorkflowAdvice, { props: { draft: { title: 'User title' } } })
      : mount(ImproveButton, { props: { draft: { title: 'User title' } } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('The agent did not complete')
    await language('cs')
    expect(wrapper.get('[role="alert"]').text()).toContain('Agent nedokončil validní návrh')
    await language('en')
    expect(wrapper.get('[role="alert"]').text()).toContain('The agent did not complete')
  })

  it.each(['workflow', 'task'])('translates a retained %s validation failure and preserves its diagnostic', async (kind) => {
    const diagnostic = 'proposed workflow is unavailable'
    const fetch = vi.fn(async () => ok({ job_id: 'invalid', state: 'failed', error_code: 'advice_invalid', error: diagnostic }))
    vi.stubGlobal('fetch', fetch)
    const wrapper = kind === 'workflow'
      ? mount(WorkflowAdvice, { props: { draft: { title: 'User title' } } })
      : mount(ImproveButton, { props: { draft: { title: 'User title' } } })
    await wrapper.get('button').trigger('click')
    await flushPromises()
    const calls = fetch.mock.calls.length
    const details = wrapper.get('[data-test="advice-error-details"]')
    ;(details.element as HTMLDetailsElement).open = true
    for (const locale of ['en', 'cs', 'en'] as const) {
      await language(locale)
      expect(wrapper.get('[role="alert"]').text()).toBe(locale === 'en'
        ? 'The advice is invalid. Review the technical details and try again.'
        : 'Návrh není platný. Zkontroluj technické podrobnosti a zkus to znovu.')
      expect(wrapper.get('[data-test="advice-error-details"] pre').text()).toBe(diagnostic)
      expect(wrapper.get('[data-test="advice-error-details"] summary').text()).toBe(locale === 'en'
        ? 'Technical details' : 'Technické podrobnosti')
      expect((wrapper.get('[data-test="advice-error-details"]').element as HTMLDetailsElement).open).toBe(true)
      expect(fetch).toHaveBeenCalledTimes(calls)
    }
  })

  it('updates state maps, progress metadata and inherited switch options', async () => {
    const toggle = mount(AutoContinueToggle, { props: { mode: 'inherit', effective: true, busy: false } })
    const item = { kind: 'agent_start', code: 'agent_start', text: 'legacy prose', ts: '', params: { name: 'proposer', model: 'model-x' } }
    expect(STATE_LABELS.ready).toBe('Ready')
    expect(COLUMN_LABELS.deferred).toBe('Deferred')
    expect(intentProgressText(item)).toBe('Agent proposer is working (model-x)')
    expect(unmetLine({ id: 'T1', reason: 'not_done', missing: [] })).toBe('T1 – task is not done')
    await language('cs')
    expect(STATE_LABELS.ready).toBe('Připraveno')
    expect(COLUMN_LABELS.deferred).toBe('Odloženo')
    expect(toggle.get('[data-test="auto-inherit"]').text()).toBe('Zděděno')
    expect(intentProgressText(item)).toBe('Agent proposer pracuje (model-x)')
    expect(intentProgressText({ kind: 'tool_call', text: 'Read soubor', ts: '' })).toBe('Read soubor')
  })

  it.each([0, 1, 2, 5, 1.5])('uses catalog plurals for %s findings and problems', async (count) => {
    expect(t('backlog.findings', { count }, count)).toBe(`${count} ${count === 1 ? 'finding' : 'findings'}`)
    await language('cs')
    const noun = count === 1 ? 'nález' : count === 2 ? 'nálezy' : count === 1.5 ? 'nálezu' : 'nálezů'
    expect(t('backlog.findings', { count }, count)).toBe(`${count} ${noun}`)
    expect(t('backlog.problems', { count }, count)).toContain(`${count} probl`)
  })
})
