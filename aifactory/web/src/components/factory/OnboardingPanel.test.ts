import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import OnboardingPanel from './OnboardingPanel.vue'
import { onboardingRequest } from '@/lib/onboarding'

const plan = { action: 'onboard', digest: 'digest', base: 'main', files: [{ path: '.factory/config.yaml', content: 'base: main', diff: '', binary: false }], blockers: [], library: { name: 'team' }, remote: { name: 'origin' }, library_plan: { items: [{ type: 'agent', name: 'builder', action: 'create', version: 'v2' }], files: [] }, report: [{ code: 'new_item', subject: 'builder', message: 'Imported' }] }
function stub(data: unknown = plan, code?: string) {
  const mock = vi.fn(async (url: string, _init?: RequestInit) => new Response(JSON.stringify({ ok: !code, data: url.endsWith('/apply') ? { library_commit: 'lib-sha', commit: 'repo-sha' } : data, warnings: [], error: code ? { code, message: code, issues: [] } : null })))
  vi.stubGlobal('fetch', mock)
  return mock
}
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })
it('previews three sections and confirms both commits without sending paths or contents', async () => {
  const mock = stub()
  const wrapper = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'onboard' } })
  await flushPromises()
  for (const section of ['library', 'repo', 'report']) expect(wrapper.find(`[data-test="onboarding-${section}"]`).exists()).toBe(true)
  expect(wrapper.text()).toContain('base: main')
  expect(wrapper.text()).toContain('nová položka')
  await wrapper.get('[data-test="onboarding-perform"]').trigger('click')
  expect(document.body.textContent).toContain('Commitnout 1 položek do knihovny team a pushnout, pak commitnout 1 souborů do main a pushnout na origin? adws/ zůstane beze změny.')
  ;(document.querySelector('[data-test="confirm-ok"]') as HTMLElement).click()
  await flushPromises()
  expect(mock.mock.calls[1]?.[0]).toBe('/api/repos/repo/factory/apply')
  expect(JSON.parse(String(mock.mock.calls[1]?.[1]?.body))).toEqual({ action: 'onboard', options: {}, target: 'base', digest: 'digest' })
  expect(wrapper.get('[data-test="onboarding-success"]').text()).toContain('lib-sha')
  expect(onboardingRequest('onboard', 'base', 'digest', 'message')).toEqual({ action: 'onboard', options: {}, target: 'base', digest: 'digest', message: 'message' })
})
it.each(['onboarded_in_remote', 'onboarding_pending'])('shows blocker %s and disables extraction', async code => {
  stub({ ...plan, pending_pr: { id: '42', url: 'https://example.test/pull/42' }, blockers: [{ code, message: 'blocked', fix: 'repair' }] }, code)
  const wrapper = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'onboard' } })
  await flushPromises()
  expect(wrapper.get('[data-test="onboarding-perform"]').attributes('disabled')).toBeDefined()
  expect(wrapper.text()).toContain(code === 'onboarded_in_remote' ? 'Stáhnout konfiguraci z base, pak převzít' : 'Čeká v PR #42')
})
it('offers cloning the manifest remote when adopting without a library', async () => {
  stub({ remote: '/bare/team.git' }, 'library_missing')
  const wrapper = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'adopt' } })
  await flushPromises()
  expect(wrapper.get('[data-test="adopt-clone"]').text()).toContain('/bare/team.git')
  expect(wrapper.get('[data-test="adopt-clone"]').attributes('disabled')).toBeUndefined()
  expect(wrapper.find('[data-test="onboarding-perform"]').exists()).toBe(false)
})
it('adopts missing items, warns about another library and offers no extraction', async () => {
  stub({ action: 'adopt', digest: 'adopt', base: 'main', library: { name: 'other', matches: false }, manifest_library: { name: 'team' }, plan: plan.library_plan, items: [{ type: 'agent', name: 'builder', state: 'missing', adopt: 'import' }] })
  const wrapper = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'adopt' } })
  await flushPromises()
  expect(wrapper.text()).toContain('Jiná knihovna')
  expect(wrapper.get('[data-test="onboarding-perform"]').text()).toBe('Doplnit knihovnu')
  expect(wrapper.text()).not.toContain('Onboarding — jednou')
  expect(onboardingRequest('adopt', 'pr', 'digest', 'ignored')).toEqual({ action: 'adopt', options: {}, target: 'base', digest: 'digest' })
})
it('shows an error without a code without a leading colon, and the PR in a new tab', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
  const wrapper = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'onboard' } })
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toBe('offline')
  vi.unstubAllGlobals()
  stub({ ...plan, pending_pr: { id: '42', url: 'https://example.test/pull/42' } }, 'onboarding_pending')
  const pending = mount(OnboardingPanel, { props: { repoId: 'repo', action: 'onboard' } })
  await flushPromises()
  const link = pending.get('a[href="https://example.test/pull/42"]')
  expect(link.attributes('target')).toBe('_blank')
  expect(link.attributes('rel')).toBe('noopener')
})
