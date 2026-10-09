import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import SetupView from './SetupView.vue'
import { answerDialog, openDialog } from '@/test/modal'
import { findingGroup } from '@/lib/library'
import type { CheckFinding } from '@/lib/api'
const finding = (code: string, scope: CheckFinding['scope'] = 'machine'): CheckFinding => ({ code, scope, severity: 'error', message: code, fix: 'git config --global user.name Test', action: null })
function envelope(data: unknown, ok = true) { return new Response(JSON.stringify({ ok, data, error: ok ? null : { code: 'checks_failed', message: 'failed' }, warnings: [] })) }
function api(exists = false, remote: string | null = null) {
  let ready = exists
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.startsWith('/api/machine/check')) return envelope({ ok: false, findings: [finding('git_identity_missing'), finding('library_missing', 'library')], harness_repos: { claude: 2 }, checked_at: 'now' }, false)
    if (url === '/api/library') return envelope({ exists: ready, library: '/home/.haifa/library', remote, ahead: 1, behind: 0 })
    if (url === '/api/library/plan') return envelope({ digest: 'reviewed', library: '/home/.haifa/library', files: [{ path: 'agent.yaml', content: 'SECRET CONTENT', diff: '', binary: false }], items: [], blockers: [] })
    if (url === '/api/library/apply') { ready = true; return envelope({ commit: 'abc' }) }
    if (url === '/api/library/push' || url === '/api/library/pull') return envelope({ after: 'abc' })
    if (url === '/api/repos') return envelope({ repos: [], home: '/home' })
    if (url === '/api/dashboard/settings') return envelope({ port: 4700, home: '/home/.haifa', registry: '/home/.haifa/dashboard.yaml', restart_required: false })
    throw new Error(`unexpected ${url} ${init?.method}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
describe('This computer', () => {
  it('groups machine findings and accepts reports in failed envelopes', async () => {
    expect(['git_missing', 'uv_missing', 'just_missing'].map(c => findingGroup(finding(c)))).toEqual(['Nástroje', 'Nástroje', 'Nástroje'])
    expect(findingGroup(finding('harness_login'))).toBe('Harnessy')
    expect(findingGroup(finding('gh_login'))).toBe('Hosting')
    expect(findingGroup(finding('factory_version'))).toBe('HAIFA')
    expect(findingGroup(finding('env_override'))).toBe('Prostředí')
    api()
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.findAll('[data-group]').map(g => g.attributes('data-group'))).toEqual(['HAIFA', 'Nástroje', 'Harnessy', 'Hosting', 'Knihovna', 'Prostředí'])
    expect(wrapper.get('[data-group="Nástroje"]').text()).toContain('git_identity_missing')
    expect(wrapper.get('[data-test="harness-counts"]').text()).toContain('claude · 2 repa')
    expect(wrapper.get('[data-group="Nástroje"]').text()).toContain('chyba · git_identity_missing')
  })
  it('copies a repair and requests a fresh check', async () => {
    const fetchMock = api(); const writeText = vi.fn(async () => {})
    vi.stubGlobal('navigator', { clipboard: { writeText } })
    const wrapper = mount(SetupView); await flushPromises()
    await wrapper.findAll('[data-test="copy-fix"]')[0]!.trigger('click'); await flushPromises()
    expect(writeText).toHaveBeenCalledWith('git config --global user.name Test')
    expect(wrapper.text()).toContain('Zkopírováno')
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/machine/check?fresh=1')
  })
  it('disables sync for a library without a remote', async () => {
    api(true)
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.text()).toContain('Bez remote')
    for (const button of wrapper.findAll('button').filter(b => ['Stáhnout', 'Odeslat'].includes(b.text()))) expect(button.attributes('disabled')).toBeDefined()
  })
  it.each(['init', 'clone'])('reviews and confirms %s using only choices and digest', async action => {
    const fetchMock = api(); const wrapper = mount(SetupView, { attachTo: document.body }); await flushPromises()
    if (action === 'clone') await wrapper.get('[data-test="library-url"]').setValue('https://example/library.git')
    await wrapper.get(`[data-test="library-${action}"]`).trigger('click'); await flushPromises()
    expect(openDialog()?.textContent).toContain('SECRET CONTENT')
    expect(fetchMock.mock.calls.some(([url]) => url === '/api/library/apply')).toBe(false)
    await answerDialog(true)
    const call = fetchMock.mock.calls.find(([url]) => url === '/api/library/apply')!
    expect(JSON.parse(call[1]!.body as string)).toEqual({ action, options: action === 'clone' ? { url: 'https://example/library.git' } : {}, digest: 'reviewed' })
    expect(wrapper.text()).toContain('Knihovna připravena')
  })
  it('replaces errors on reload, copies only a real fix and leads to adding a repo', async () => {
    let failing = true
    const fetchMock = vi.fn(async (url: string) => {
      if (url.startsWith('/api/machine/check')) {
        if (failing) throw new Error('offline')
        return envelope({ ok: true, findings: [{ code: 'env_override', scope: 'machine', severity: 'warning', message: 'm', fix: null, action: null }], checked_at: '2026-10-01T10:00:00Z' })
      }
      if (url === '/api/library') return envelope({ exists: true, library: '/lib', remote: 'origin' })
      if (url === '/api/repos') return envelope({ repos: [], home: '/home' })
      if (url === '/api/dashboard/settings') return envelope({ port: 4700, home: '/h', registry: '/h/r', restart_required: false })
      if (url === '/api/library/pull') return envelope({})
      throw new Error(`unexpected ${url}`)
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(SetupView); await flushPromises()
    expect(wrapper.get('[data-test="setup-error"]').text()).toBe('Kontrola počítače selhala: offline')
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-test="setup-error"]').text()).toBe('Kontrola počítače selhala: offline')
    failing = false
    await wrapper.get('[data-test="machine-refresh"]').trigger('click'); await flushPromises()
    expect(wrapper.find('[data-test="setup-error"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="copy-fix"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="machine-finding"]').text()).toContain('varování · env_override')
    expect(wrapper.find('[data-test="dashboard-settings"]').exists()).toBe(true)
    expect(wrapper.get('[data-test="add-repo-link"]').text()).toBe('Další krok: Přidat repozitář')
    expect(wrapper.get('[data-test="add-repo-link"]').attributes('href')).toBe('#/repos/add')
    await wrapper.get('[data-test="library-pull"]').trigger('click')
    expect(wrapper.get('[data-test="setup-busy"]').text()).toBe('Ukládám…')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/library/pull', expect.objectContaining({ method: 'POST' }))
    expect(wrapper.text()).toContain('Stažení dokončeno')
  })
})
