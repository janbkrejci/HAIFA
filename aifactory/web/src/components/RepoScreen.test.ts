import { afterEach, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoScreen from './RepoScreen.vue'
import { resetConfigStatusForTests } from '@/lib/configStatus'
import { resetBacklogStatusForTests } from '@/lib/backlogStatus'
import { resetNamesForTests } from '@/lib/names'
import { resetLiveForTests } from '@/lib/live'
import { factoryCheck, installPlan } from '@/test/factoryFixtures'
import { CLEAN_STATUS, DIRTY_STATUS } from '@/test/settingsFixtures'
import { answerDialog } from '@/test/modal'

enableAutoUnmount(afterEach)
afterEach(() => {
  resetConfigStatusForTests(); resetBacklogStatusForTests(); resetNamesForTests(); resetLiveForTests()
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})
it('routes the banner to a reviewed commit and refreshes status only after applying', async () => {
  let applied = false
  const fetchMock = vi.fn(async (url: string) => {
    let data: unknown = { items: [], levels: [], tasks: [] }
    if (url.endsWith('/factory/roster')) data = { agents: [], workflow_tasks: {} }
    if (url === '/api/library') data = { exists: true, items: [] }
    if (url === '/api/repos') data = { repos: [] }
    if (url.endsWith('/config/status')) data = applied ? CLEAN_STATUS : DIRTY_STATUS
    if (url.includes('/factory/check')) data = factoryCheck()
    if (url.endsWith('/factory/plan')) data = { ...installPlan(), action: 'config_commit' }
    if (url.endsWith('/factory/apply')) { applied = true; data = { commit: 'config-result' } }
    if (url === '/api/overview') data = { repos: [{ id: 'haifa', state: 'ok', running: [] }], totals: {} }
    return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
  })
  vi.stubGlobal('fetch', fetchMock)
  window.location.hash = '#/r/haifa/backlog'; window.dispatchEvent(new HashChangeEvent('hashchange'))
  const w = mount(RepoScreen, { attachTo: document.body }); await flushPromises()
  await w.get('[data-test="config-commit"]').trigger('click')
  window.dispatchEvent(new HashChangeEvent('hashchange')); await flushPromises()
  expect(w.get('[data-test="factory-plan"]').text()).toContain('.factory/manifest.yaml')
  expect(applied).toBe(false)
  await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
  expect(applied).toBe(true)
  expect(w.find('[data-test="config-banner"]').exists()).toBe(false)
  expect(fetchMock.mock.calls.some(([url]) => url.endsWith('/factory/check?fresh=1'))).toBe(true)
})
