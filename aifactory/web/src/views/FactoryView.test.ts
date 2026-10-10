import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import FactoryView from './FactoryView.vue'
import type { CheckFinding, FactoryCheck } from '@/lib/api'
import { lastFactoryResult } from '@/lib/factory'
import { useRouteParams } from '@/lib/router'
import { backlogData, runCheck, runStart, taskDetail, taskNode } from '@/test/backlogFixtures'

function finding(code: string, scope: CheckFinding['scope'], severity: CheckFinding['severity'] = 'warning'): CheckFinding {
  return { code, scope, severity, message: `${code} message`, fix: `fix ${code}`, action: null }
}

function report(extra: Partial<FactoryCheck> = {}): FactoryCheck {
  return {
    in_repo: true,
    repo: '/w/repo',
    state: 'onboarded',
    action: null,
    sssf_leftover: false,
    alternate_rosters: false,
    onboarding: null,
    base: 'main',
    commit: '0123456789abcdef',
    remote: 'origin',
    ahead: 0,
    behind: 2,
    offline: false,
    ok: true,
    counts: { error: 0, warning: 0, info: 0 },
    findings: [],
    checked_at: '2026-10-01T10:00:00+00:00',
    cached: false,
    manifest: { format: 1, written_by: 'haifa 0.1.0' },
    manifest_error: null,
    version: '0.1.0',
    ...extra,
  }
}

function stub(...answers: Response[]) {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => {
    if (url.endsWith('/factory/plan') && JSON.parse(String(_init?.body)).action === 'adopt') return ok({ action: 'adopt', digest: 'adopt', base: 'main', items: [], plan: null })
    if (url.endsWith('/factory/plan') && JSON.parse(String(_init?.body)).action === 'config_commit') return ok({ action: 'config_commit', base: 'main', base_sha: 'abc', digest: 'cfg', files: [], blockers: [] })
    if (url.endsWith('/factory/items')) return ok({ items: [] })
    if (url.startsWith('/api/machine/check')) return ok({ ok: true, findings: [], checked_at: 'now', cached: false, harness_repos: { claude: 0, codex: 0 } })
    if (url === '/api/machine/harnesses') return ok({ settings: { harnesses: {} }, available: {}, models: {} })
    if (url.endsWith('/factory/roster')) return ok({ agents: [], workflow_tasks: {} })
    if (url.endsWith('/library')) return ok({ exists: true, items: [] })
    if (url.endsWith('/repos')) return ok({ repos: [] })
    if (url.endsWith('/backlog/task-advice/options')) {
      return ok({ default: { harness: 'claude', model: 'sonnet' }, harnesses: [{ name: 'claude', default_model: 'sonnet', models: ['sonnet'] }] })
    }
    return answers.shift() ?? ok(report())
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

function failed(code: string, data: unknown, status = 200) {
  return new Response(
    JSON.stringify({ ok: false, data, error: { code, message: `${code} message`, path: null, id: null, issues: [] }, warnings: [] }),
    { status },
  )
}

enableAutoUnmount(afterEach)

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FactoryView', () => {
  it('opens the configuration commit preview when entered through the banner route', async () => {
    const fetchMock = stub(ok(report()))
    window.location.hash = '#/r/haifa/factory/config_commit'
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    useRouteParams().value = ['config_commit']
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.find('[data-test="factory-operation"]').exists()).toBe(true)
    expect(Array.from(wrapper.element.children).indexOf(wrapper.get('[data-test="factory-operation"]').element)).toBeLessThan(Array.from(wrapper.element.children).indexOf(wrapper.get('[data-test="factory-summary"]').element))
    expect(fetchMock.mock.calls.some(([url, init]) => url.endsWith('/factory/plan') && JSON.parse(String(init?.body)).action === 'config_commit')).toBe(true)
  })

  it('runs the check on mount and shows the manifest, the version and the state', async () => {
    const fetchMock = stub(ok(report()))
    const wrapper = mount(FactoryView)
    expect(wrapper.find('[data-test="factory-loading"]').exists()).toBe(true)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/factory/check')
    const summary = wrapper.get('[data-test="factory-summary"]')
    expect(summary.text()).toContain('Factory je v pořádku')
    expect(summary.get('[data-test="factory-manifest"]').text()).toBe('formát 1, zapsal haifa 0.1.0')
    expect(summary.get('[data-test="factory-version"]').text()).toBe('0.1.0')
    expect(summary.get('[data-test="factory-state"]').text()).toBe('Onboardováno')
    expect(summary.get('[data-test="factory-base"]').text()).toContain('main@01234567')
    expect(wrapper.get('[data-test="findings-repo"]').text()).toContain('Bez nálezů')
    expect(wrapper.get('[data-test="findings-local"]').text()).toContain('Bez nálezů')
  })

  it('offers install without update or roster on a repo without factory', async () => {
    stub(ok(report({ state: 'none', manifest: null })))
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.find('[data-test="factory-open-init"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="factory-open-update"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="roster-editor"]').exists()).toBe(false)
  })

  it('names the pull of base config apart from the Review base sync', async () => {
    stub(ok(report({ behind: 2 })))
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.get('[data-test="factory-open-pull"]').text()).toBe('Stáhnout konfiguraci z base')
    expect(wrapper.find('[data-test="roster-editor"]').exists()).toBe(true)
  })

  it('lists what next after an install here', async () => {
    lastFactoryResult.value = { repoId: 'haifa', result: { commit: 'abc' }, action: 'init' }
    stub(ok(report()))
    const wrapper = mount(FactoryView)
    await flushPromises()
    const next = wrapper.get('[data-test="factory-next-steps"]')
    expect(next.text()).toContain('Co dál')
    expect(next.get('[data-test="next-project"]').attributes('href')).toBe('#/r/haifa/backlog/new-container')
    await next.get('[data-test="next-commit"]').trigger('click')
    expect(wrapper.find('[data-test="factory-operation"]').exists()).toBe(true)
    lastFactoryResult.value = null
  })

  it('says there is no manifest and shows the onboarding', async () => {
    stub(
      ok(
        report({
          state: 'pre_library',
          manifest: null,
          onboarding: { source: 'init', source_commit: null, at: '2026-10-01T10:00:00+00:00', by: 'Ada', factory: '0.1.0', library_commit: null },
          cached: true,
        }),
      ),
    )
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.get('[data-test="factory-manifest"]').text()).toBe('bez manifestu')
    expect(wrapper.get('[data-test="factory-onboarding"]').text()).toContain('Onboardoval Ada')
    expect(wrapper.get('[data-test="factory-onboarding"]').text()).toContain('z factory init')
    expect(wrapper.get('[data-test="factory-checked"]').text()).toContain('(z mezipaměti)')
  })

  it('renders a checks_failed envelope as the report, findings grouped by scope', async () => {
    const findings = [
      finding('agent_unknown', 'repo', 'info'),
      finding('config_invalid', 'repo', 'error'),
      finding('gh_missing', 'machine', 'warning'),
      finding('library_stale', 'library', 'error'),
    ]
    stub(failed('checks_failed', report({ ok: false, counts: { error: 2, warning: 1, info: 1 }, findings })))
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.find('[data-test="factory-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="factory-summary"]').text()).toContain('2 chyb, 1 varování')
    const repo = wrapper.get('[data-test="findings-repo"]')
    expect(repo.text()).toContain('Repozitář: opravit a commitnout')
    expect(repo.findAll('[data-test="finding"]').map((f) => f.attributes('data-severity'))).toEqual(['error', 'info'])
    expect(repo.text()).toContain('Oprava: fix config_invalid')
    const local = wrapper.get('[data-test="findings-local"]')
    expect(local.text()).toContain('Tento počítač: opravit lokálně')
    const items = local.findAll('[data-test="finding"]')
    expect(items.map((f) => f.text())).toEqual([expect.stringContaining('library_stale'), expect.stringContaining('gh_missing')])
    expect(items[0].find('[data-test="finding-library"]').text()).toBe('knihovna')
    expect(items[1].find('[data-test="finding-library"]').exists()).toBe(false)
  })

  it('shows another error as text', async () => {
    stub(failed('not_a_repository', null, 422))
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.get('[data-test="factory-error"]').text()).toContain('not_a_repository message')
  })

  it('checks again with fresh=1', async () => {
    const fetchMock = stub(ok(report()), ok(report({ version: '0.2.0' })))
    const wrapper = mount(FactoryView)
    await flushPromises()
    await wrapper.get('[data-test="factory-recheck"]').trigger('click')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/factory/check?fresh=1')
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/factory/items'))).toHaveLength(2)
    expect(wrapper.get('[data-test="factory-version"]').text()).toBe('0.2.0')
  })

  it('selects individual findings, creates a repair task and starts its run after committing', async () => {
    const findings = [finding('same_code', 'repo'), finding('same_code', 'repo'), finding('gh_missing', 'machine')]
    findings[1].message = 'second occurrence'
    const task = taskNode({ writes: ['src/'], depends_on: [] })
    const fetchMock = stub(
      ok(report({ findings })), ok(backlogData()),
      ok({ task }), ok(runCheck({ in_base: false })),
      ok({ committed: true }), ok(runCheck()), ok(runStart()),
    )
    const wrapper = mount(FactoryView)
    await flushPromises()
    expect(wrapper.get('[data-test="factory-repair-open"]').attributes('disabled')).toBeDefined()
    await wrapper.findAll('[data-test="finding-select"]')[1].setValue(true)
    await wrapper.findAll('[data-test="finding-select"]')[2].setValue(true)
    expect(wrapper.get('[data-test="factory-selected-count"]').text()).toBe('Vybráno: 2')
    await wrapper.get('[data-test="factory-repair-open"]').trigger('click')
    await flushPromises()
    const body = wrapper.get('[data-test="body"]')
    expect((body.element as HTMLTextAreaElement).value).toContain('second occurrence')
    expect((body.element as HTMLTextAreaElement).value).toContain('gh_missing (machine, warning)')
    expect((body.element as HTMLTextAreaElement).value).toContain('Doporučená oprava: fix gh_missing')
    expect((body.element as HTMLTextAreaElement).value).not.toContain('same_code message')
    await wrapper.get('[data-test="writes"]').setValue('src/')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const create = fetchMock.mock.calls.find(([url]) => url.endsWith('/backlog/tasks'))
    expect(JSON.parse(create![1]!.body as string)).toMatchObject({ title: 'Opravit vybrané nálezy Factory', writes: ['src/'] })
    expect(wrapper.get('[data-test="run-start"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="commit-backlog"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.some(([url]) => url.endsWith(`/${task.id}/run`))).toBe(true)
    expect(wrapper.get('[data-test="run-result"] a').attributes('href')).toContain('/runs/')
    expect(wrapper.get('[data-test="run-start"]').attributes('disabled')).toBeDefined()
  })

  it('clears the selection after a fresh check and keeps deselected findings out of the repair', async () => {
    stub(ok(report({ findings: [finding('old', 'repo')] })), ok(report({ findings: [finding('new', 'repo')] })))
    const wrapper = mount(FactoryView)
    await flushPromises()
    await wrapper.get('[data-test="finding-select"]').setValue(true)
    await wrapper.get('[data-test="finding-select"]').setValue(false)
    expect(wrapper.get('[data-test="factory-repair-open"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-test="finding-select"]').setValue(true)
    await wrapper.get('[data-test="factory-recheck"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="factory-selected-count"]').text()).toBe('Vybráno: 0')
    expect((wrapper.get('[data-test="finding-select"]').element as HTMLInputElement).checked).toBe(false)
  })

  it('shows backlog loading failures and allows retry without losing selected findings', async () => {
    stub(ok(report({ findings: [finding('repair_me', 'repo')] })), failed('invalid_config', null, 422), ok(backlogData()))
    const wrapper = mount(FactoryView)
    await flushPromises()
    await wrapper.get('[data-test="finding-select"]').setValue(true)
    await wrapper.get('[data-test="factory-repair-open"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="factory-repair"] [role="alert"]').text()).toContain('invalid_config')
    await wrapper.get('[data-test="factory-repair"] button').trigger('click')
    await flushPromises()
    expect((wrapper.get('[data-test="body"]').element as HTMLTextAreaElement).value).toContain('repair_me')
  })

  it('keeps the created task on start failure and resolves a pending start without launching twice', async () => {
    const task = taskNode({ writes: ['src/'] })
    const fetchMock = stub(
      ok(report({ findings: [finding('repair_me', 'repo')] })), ok(backlogData()),
      ok({ task }), ok(runCheck()), failed('already_running', null, 409),
      ok(runStart({ pending: true, run: null })), ok(taskDetail({ task, runs: [] })),
      ok(taskDetail({ task, runs: [runStart().run!] })),
    )
    const wrapper = mount(FactoryView)
    await flushPromises()
    await wrapper.get('[data-test="finding-select"]').setValue(true)
    await wrapper.get('[data-test="factory-repair-open"]').trigger('click')
    await flushPromises()
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    await wrapper.get('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="run-dialog"]').text()).toContain('already_running')
    await wrapper.get('[data-test="run-start"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="run-start"]').attributes('disabled')).toBeDefined()
    const refresh = wrapper.get('[data-test="factory-repair"]').findAll('button').find(b => b.text() === 'Obnovit stav běhu')!
    await refresh.trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="run-result"] a').attributes('href')).toContain('/runs/')
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith('/backlog/tasks'))).toHaveLength(1)
    expect(fetchMock.mock.calls.filter(([url]) => url.endsWith(`/${task.id}/run`))).toHaveLength(2)
  })
})


it('reopens a fresh preview when the same operation is selected again', async () => {
  const plan = { action: 'config_commit', base: 'main', base_sha: 'a6f3e1c', digest: 'd', files: [], blockers: [] }
  const fetchMock = stub(ok(report()), ok(plan), ok({ repos: [], totals: {} }), ok(plan), ok({ repos: [], totals: {} }))
  const wrapper = mount(FactoryView)
  await flushPromises()
  await wrapper.get('[data-test="factory-open-config_commit"]').trigger('click'); await flushPromises()
  await wrapper.get('[data-test="factory-open-config_commit"]').trigger('click'); await flushPromises()
  expect(fetchMock.mock.calls.filter(([url, init]) => url.endsWith('/factory/plan') && JSON.parse(String(init?.body)).action === 'config_commit')).toHaveLength(2)
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/apply'))).toBe(false)
})
