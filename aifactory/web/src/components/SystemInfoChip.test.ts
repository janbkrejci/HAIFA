import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import SystemInfoChip from './SystemInfoChip.vue'
import { answerDialog, openDialog } from '@/test/modal'
import type { SystemInfo } from '@/lib/system'

const GB = 1024 ** 3
function system(status: SystemInfo['status'] = 'ok', free: number | null = 8 * GB): SystemInfo {
  return {
    status,
    volumes: [
      { id: 'C:', paths: ['C:/haifa', 'C:/repos'], free: 40 * GB, total: 100 * GB, status },
      { id: 'D:', paths: ['D:/repo'], free: null, total: null, status: 'ok' },
    ],
    memory: { free, total: free === null ? null : 16 * GB, status },
  }
}
function envelope(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}
function stubApi(info = system()) {
  const fetchMock = vi.fn(async (url: string, _init?: RequestInit) => envelope(url === '/api/machine/system' ? info : {
    advice_directories: ['orphan'],
    repos: [{ repo: 'repo', removed: [{ worktree: 'done' }], deleted_branches: ['merged'], warnings: ['kept dirty tree'] }],
    freed_bytes: GB,
    warnings: ['kept dirty tree'],
  }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers() })

describe('SystemInfoChip', () => {
  it.each(['ok', 'warning'] as const)('shows %s and all resource values in the accessible tooltip', async status => {
    stubApi(system(status))
    const wrapper = mount(SystemInfoChip)
    const chip = wrapper.get('[data-test="system-info-chip"]')
    await nextTick()
    expect(chip.find('.spinner').exists()).toBe(true)
    expect(chip.attributes('disabled')).toBeDefined()
    await flushPromises()
    expect(chip.text()).toBe('')
    expect(chip.classes()).toContain(status === 'ok' ? 'success' : 'warning')
    expect(chip.find(status === 'ok' ? '.lucide-hard-drive' : '.lucide-triangle-alert').exists()).toBe(true)
    await chip.trigger('focusin')
    const text = document.body.querySelector('[role="tooltip"]')?.textContent
    expect(text).toBe(chip.attributes('aria-label'))
    for (const value of ['C:/haifa, C:/repos', '40 GB / celkem 100 GB', 'D:/repo', 'nedostupné', 'Paměť: volná 8 GB / celkem 16 GB', 'Kliknutím uklidíš disk']) expect(text).toContain(value)
  })

  it('shows unavailable memory without treating it as low memory', async () => {
    stubApi(system('ok', null))
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    const chip = wrapper.get('button')
    expect(chip.attributes('aria-label')).toContain('Paměť: volná nedostupné / celkem nedostupné')
    expect(chip.classes()).toContain('success')
  })

  it('cancels cleanup without sending a POST', async () => {
    vi.useFakeTimers()
    const fetchMock = stubApi()
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    await wrapper.get('button').trigger('click')
    expect(openDialog()?.textContent).toContain('osiřelé dočasné adresáře návrhů')
    expect(openDialog()?.textContent).toContain('hotové worktrees a větve sloučených PR ve všech repech')
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchMock).toHaveBeenCalledTimes(1)
    await answerDialog(false)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('confirms cleanup, shows a spinner, counts removed items and refreshes resources', async () => {
    const fetchMock = stubApi()
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    let finish!: (response: Response) => void
    fetchMock.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    await wrapper.get('button').trigger('click')
    await answerDialog(true)
    expect(fetchMock).toHaveBeenLastCalledWith('/api/machine/cleanup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
    expect(wrapper.get('button').attributes('disabled')).toBeDefined()
    expect(wrapper.find('.spinner').exists()).toBe(true)
    fetchMock.mockResolvedValueOnce(envelope(system('warning', GB)))
    finish(envelope({ advice_directories: ['orphan'], repos: [{ removed: [{}], deleted_branches: ['branch'] }], freed_bytes: GB, warnings: ['kept dirty tree'] }))
    await flushPromises()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/machine/system')
    const chip = wrapper.get('button')
    expect(chip.attributes('aria-label')).toContain('odstraněno 3 položek, uvolněné místo: 1 GB')
    expect(chip.attributes('aria-label')).toContain('kept dirty tree')
    expect(chip.attributes('aria-label')).toContain('Paměť: volná 1 GB')
    expect(chip.classes()).toContain('warning')
  })

  it('shows load errors and recovers on the next minute; stops polling on unmount', async () => {
    vi.useFakeTimers()
    const fetchMock = stubApi()
    fetchMock.mockRejectedValueOnce(new Error('offline'))
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    expect(wrapper.get('button').attributes('aria-label')).toContain('offline')
    expect(wrapper.get('button').classes()).toContain('warning')
    await vi.advanceTimersByTimeAsync(60_000)
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(wrapper.get('button').attributes('aria-label')).not.toContain('offline')
    wrapper.unmount()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shows cleanup errors and still refreshes resources', async () => {
    const fetchMock = stubApi()
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: false, data: null, error: { code: 'cleanup_busy', message: 'Úklid už běží' } })))
    await wrapper.get('button').trigger('click')
    await answerDialog(true)
    expect(wrapper.get('button').attributes('aria-label')).toContain('Úklid se nepodařil: Úklid už běží')
    expect(wrapper.get('button').attributes('disabled')).toBeUndefined()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/machine/system')
  })

  it('shows an invalid response as an error without crashing the topbar', async () => {
    stubApi().mockResolvedValueOnce(envelope({}))
    const wrapper = mount(SystemInfoChip)
    await flushPromises()
    expect(wrapper.get('button').attributes('aria-label')).toContain('Neplatná odpověď systému')
    expect(wrapper.get('button').classes()).toContain('warning')
  })
})
