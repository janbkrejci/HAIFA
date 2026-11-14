import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import SetupView from './SetupView.vue'
import LibrarySection from '@/components/setup/LibrarySection.vue'
import { answerDialog, openDialog } from '@/test/modal'
import { findingGroup } from '@/lib/library'
import { useRouteParams } from '@/lib/router'
import type { CheckFinding } from '@/lib/api'
const finding = (code: string, scope: CheckFinding['scope'] = 'machine'): CheckFinding => ({ code, scope, severity: 'error', message: code, fix: 'git config --global user.name Test', action: null })
function envelope(data: unknown, ok = true) { return new Response(JSON.stringify({ ok, data, error: ok ? null : { code: 'checks_failed', message: 'failed' }, warnings: [] })) }
function api(exists = false, remote: string | null = null) {
  let ready = exists
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/machine/check')) return envelope({ ok: false, findings: [finding('git_identity_missing'), finding('library_missing', 'library')], harness_repos: { claude: 2 }, checked_at: 'now' }, false)
    if (url === '/api/library') return envelope({ exists: ready, library: '/home/.haifa/library', remote, ahead: 1, behind: 0, default_url: 'https://github.com/janbkrejci/HAIFA-LIBRARY.git', items: [] })
    if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: [], errors: [] })
    if (url === '/api/library/plan') return envelope({ digest: 'reviewed', library: '/home/.haifa/library', files: [{ path: 'agent.yaml', content: 'SECRET CONTENT', diff: '', binary: false }], items: [], blockers: [] })
    if (url === '/api/library/apply') { ready = true; return envelope({ commit: 'abc' }) }
    if (url === '/api/library/push' || url === '/api/library/pull') return envelope({ after: 'abc' })
    if (url === '/api/dashboard/settings') return envelope({ port: 4700, home: '/home/.haifa', registry: '/home/.haifa/dashboard.yaml', restart_required: false })
    throw new Error(`unexpected ${url} ${init?.method}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
describe('Knihovna page', () => {
  it('shows only groups with findings and the library findings in the library section', async () => {
    expect(['git_missing', 'uv_missing', 'just_missing'].map(c => findingGroup(finding(c)))).toEqual(['Nástroje', 'Nástroje', 'Nástroje'])
    expect(findingGroup(finding('harness_login'))).toBe('Harnessy')
    expect(findingGroup(finding('gh_login'))).toBe('Hosting')
    expect(findingGroup(finding('factory_version'))).toBe('HAIFA')
    expect(findingGroup(finding('env_override'))).toBe('Prostředí')
    api()
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.get('h1').text()).toBe('Knihovna')
    const order = wrapper.findAll('[data-test="library"], [data-test="machine-check"], [data-test="dashboard-settings"]').map(s => s.attributes('data-test'))
    expect(order).toEqual(['library', 'machine-check', 'dashboard-settings'])
    expect(wrapper.get('[data-test="machine-check"] h2').text()).toBe('Kontrola počítače')
    expect(wrapper.get('[data-test="machine-verdict"]').text()).toBe('2 chyb, 0 varování')
    expect(wrapper.findAll('[data-group]').map(g => g.attributes('data-group'))).toEqual(['Nástroje'])
    expect(wrapper.get('[data-group="Nástroje"]').text()).toContain('chyba · git_identity_missing')
    expect(wrapper.get('[data-test="library"]').text()).toContain('library_missing')
    expect(wrapper.find('[data-test="harness-counts"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="getting-started"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="add-repo-link"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Bez nálezů')
    expect(wrapper.text()).not.toContain('HAIFA je spuštěná')
    expect(wrapper.find('[data-test="dashboard-settings"]').exists()).toBe(true)
  })
  it('copies a repair and requests a fresh check', async () => {
    const fetchMock = api(); const writeText = vi.fn(async () => {})
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(SetupView); await flushPromises()
    await wrapper.findAll('[data-test="copy-fix"]')[0]!.trigger('click'); await flushPromises()
    expect(writeText).toHaveBeenCalledWith('git config --global user.name Test')
    expect(wrapper.text()).toContain('Zkopírováno')
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
  })
  it('disables sync for a library without a remote', async () => {
    api(true)
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.get('[data-test="library-sync-state"]').text()).toContain('Bez remote')
    expect(wrapper.find('[data-test="library-pull"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="library-connect"]').exists()).toBe(true)
  })
  it.each(['init', 'clone'])('sets up the library (%s) from the section, then reads the updated state', async action => {
    const fetchMock = api(); const wrapper = mount(SetupView, { attachTo: document.body }); await flushPromises()
    const applied = vi.fn(); window.addEventListener('factory-applied', applied)
    if (action === 'clone') await wrapper.get('[data-test="library-url"]').setValue('https://example/library.git')
    await wrapper.get(`[data-test="library-${action}"]`).trigger('click'); await flushPromises()
    expect(openDialog()?.textContent).toContain('SECRET CONTENT')
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/library/apply')).toBe(false)
    await answerDialog(true)
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/library/apply')!
    expect(JSON.parse(call[1]!.body as string)).toEqual({ action, options: action === 'clone' ? { url: 'https://example/library.git' } : {}, digest: 'reviewed' })
    expect(wrapper.text()).toContain('Knihovna připravena')
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(fetchMock).not.toHaveBeenCalledWith('/api/machine/check?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(applied).toHaveBeenCalled()
    window.removeEventListener('factory-applied', applied)
  })
  it('prefills the default team library for a clone', async () => {
    const fetchMock = api(); const wrapper = mount(SetupView, { attachTo: document.body }); await flushPromises()
    expect((wrapper.get('[data-test="library-url"]').element as HTMLInputElement).value).toBe('https://github.com/janbkrejci/HAIFA-LIBRARY.git')
    await wrapper.get('[data-test="library-clone"]').trigger('click'); await flushPromises()
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/library/plan')!
    expect(JSON.parse(call[1]!.body as string)).toEqual({ action: 'clone', options: { url: 'https://github.com/janbkrejci/HAIFA-LIBRARY.git' } })
  })
  it('replaces errors on reload and shows an ok verdict', async () => {
    let failing = true
    const fetchMock = vi.fn(async (url: string) => {
      if (url.startsWith('/api/machine/check')) {
        if (failing) throw new Error('offline')
        return envelope({ ok: true, findings: [], checked_at: '2026-10-01T10:00:00Z' })
      }
      if (url === '/api/library') return envelope({ exists: true, library: '/lib', remote: 'origin', items: [] })
      if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: [], errors: [] })
      if (url === '/api/dashboard/settings') return envelope({ port: 4700, home: '/h', registry: '/h/r', restart_required: false })
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.get('[data-test="setup-error"]').text()).toBe('Kontrola počítače selhala: offline')
    failing = false
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-test="setup-error"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="machine-verdict"]').text()).toBe('Počítač je v pořádku')
    expect(wrapper.findAll('[data-group]')).toHaveLength(0)
  })
  it('scrolls to the library on #/setup/library', async () => {
    api(true)
    const scroll = vi.fn()
    const original = HTMLElement.prototype.scrollIntoView
    HTMLElement.prototype.scrollIntoView = scroll
    try {
      useRouteParams().value = ['library']
      const wrapper = mount(SetupView, { attachTo: document.body }); await flushPromises()
      expect(scroll.mock.contexts).toContain(wrapper.get('[data-test="library"]').element)
    } finally {
      HTMLElement.prototype.scrollIntoView = original
      useRouteParams().value = []
    }
  })

  function machineApi(answer: (fresh: boolean) => Promise<Response> | Response) {
    const fetchMock = vi.fn(async (url: string) => {
      if (url.startsWith('/api/machine/check')) return answer(url.endsWith('fresh=1'))
      if (url === '/api/machine/progress') return envelope({ job: { seq: 2, offline: false, step: 'machine: logins', detail: 'claude auth status', started_at: '', elapsed: 2, budget: 60, running: true }, checked_at: null })
      if (url === '/api/library') return envelope({ exists: true, library: '/lib', remote: 'origin', items: [] })
      if (url === '/api/library/overrides') return envelope({ library: 'abc', overrides: [], errors: [] })
      if (url === '/api/dashboard/settings') return envelope({ port: 4700, home: '/h', registry: '/h/r', restart_required: false })
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    return fetchMock
  }
  it.each([false, true])('warns about an unchecked or stale result and checks only on click (stale=%s)', async stale => {
    const fetchMock = machineApi(fresh => envelope({
      ok: fresh, findings: [], checked: fresh || stale,
      checked_at: fresh || stale ? '2026-11-10T10:00:00Z' : null,
      cached: stale && !fresh, stale: stale && !fresh,
    }, fresh))
    const wrapper = mount(SetupView); await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(fetchMock).not.toHaveBeenCalledWith('/api/machine/check?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.get('[data-test="machine-status"]').text()).toContain(stale ? 'Zastaralý výsledek' : 'zatím nebyl zkontrolován')
    expect(wrapper.find('[data-test="setup-busy"]').exists()).toBe(false)
    expect(wrapper.find('.is-ok').exists()).toBe(false)
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1', expect.objectContaining({ signal: expect.any(AbortSignal) }))
    expect(wrapper.find('[data-test="machine-status"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="machine-verdict"]').classes()).toContain('is-ok')
  })
  const timedOut = (checkedAt: string | null) => new Response(JSON.stringify({
    ok: false,
    data: { ok: false, findings: [], checked_at: checkedAt, cached: !!checkedAt, stale: true, timed_out: true, progress: { seq: 2, offline: false, step: 'machine: logins', detail: 'claude auth status', started_at: '', elapsed: 60, budget: 60, running: true } },
    error: { code: 'check_timeout', message: 'the check did not finish', path: null, id: null, issues: [] }, warnings: [],
  }))
  it('shows a timed-out check with its unfinished step and the age of the last known result', async () => {
    const checkedAt = new Date(Date.now() - 5 * 60_000).toISOString()
    machineApi(() => timedOut(checkedAt))
    const wrapper = mount(SetupView); await flushPromises()
    const alert = wrapper.get('[data-test="machine-timeout"]').text()
    expect(alert).toContain('Kontrola nedoběhla do 60 s. Nedokončený krok: machine: logins (claude auth status).')
    expect(alert).toContain('(před 5 min)')
    // The old result is never presented as a current success.
    expect(wrapper.get('[data-test="machine-verdict"]').text()).toBe('Poslední známý stav: Počítač je v pořádku')
    expect(wrapper.get('[data-test="machine-verdict"]').classes()).toContain('is-bad')
    expect(wrapper.get('[data-test="machine-summary"]').text()).toContain('neaktuální')
    expect(wrapper.get('[data-test="machine-refresh"]').attributes('disabled')).toBeUndefined()
  })
  it('shows no verdict for a first check that timed out', async () => {
    machineApi(() => timedOut(null))
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.get('[data-test="machine-timeout"]').text()).toContain('Dřívější výsledek není k dispozici.')
    expect(wrapper.find('[data-test="machine-verdict"]').exists()).toBe(false)
  })
  it('shows the step and elapsed time while checking, and a late older answer changes nothing', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      const answers: ((response: Response) => void)[] = []
      machineApi(() => new Promise<Response>(resolve => { answers.push(resolve) }))
      const wrapper = mount(SetupView); await flushPromises()
      await vi.advanceTimersByTimeAsync(2000)
      expect(wrapper.get('[data-test="setup-busy"]').text()).toBe('Probíhá kontrola – čeká na: machine: logins (claude auth status) · 2 s')
      // A library write reads updated rules while the first read still runs.
      wrapper.findComponent(LibrarySection).vm.$emit('changed')
      await flushPromises()
      expect(answers).toHaveLength(2)
      answers[1]!(envelope({ ok: false, findings: [finding('git_identity_missing')], checked_at: '2026-11-10T10:00:00Z', cached: false }, false))
      await flushPromises()
      expect(wrapper.get('[data-test="machine-verdict"]').text()).toBe('1 chyb, 0 varování')
      answers[0]!(envelope({ ok: true, findings: [], checked_at: '2026-11-10T09:00:00Z', cached: true }))
      await flushPromises()
      expect(wrapper.get('[data-test="machine-verdict"]').text()).toBe('1 chyb, 0 varování')
      expect(wrapper.find('[data-test="setup-busy"]').exists()).toBe(false)
    } finally { vi.useRealTimers() }
  })
  it('ends the wait at the page deadline with the step it waited for', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
    try {
      machineApi(() => new Promise<Response>(() => {}))
      const wrapper = mount(SetupView); await flushPromises()
      await vi.advanceTimersByTimeAsync(75_000)
      expect(wrapper.get('[data-test="setup-error"]').text()).toBe('Kontrola počítače selhala: Kontrola nedoběhla do 75 s; nedokončený krok: machine: logins (claude auth status)')
      expect(wrapper.find('[data-test="setup-busy"]').exists()).toBe(false)
      expect(wrapper.get('[data-test="machine-refresh"]').attributes('disabled')).toBeUndefined()
    } finally { vi.useRealTimers() }
  })
})
