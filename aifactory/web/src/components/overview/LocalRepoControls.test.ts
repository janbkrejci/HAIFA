import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import LocalRepoControls from './LocalRepoControls.vue'
import { patchLocalRepoSettings, type LocalRepoSettings } from '@/lib/api'
import { fetchHarnessSettings } from '@/lib/machineHarnesses'
import { repo } from '@/test/overviewFixtures'
import { chooseOption, selectLabels } from '@/test/select'

vi.mock('@/lib/api', async importOriginal => ({
  ...await importOriginal<typeof import('@/lib/api')>(), patchLocalRepoSettings: vi.fn(),
}))
vi.mock('@/lib/machineHarnesses', () => ({
  fetchHarnessSettings: vi.fn(async () => ({
    settings: { version: 1, default_harness: 'codex', harnesses: { codex: { enabled: true, model: 'gpt' } } },
    available: { codex: true }, models: { codex: ['gpt'] }, configured: true,
  })),
}))
enableAutoUnmount(afterEach)
afterEach(() => vi.clearAllMocks())
const local = (on = true): LocalRepoSettings => ({
  settings: { version: 1, auto_continue: on, auto_merge: false, harness: null }, effective_harness: 'codex',
})
const panel = (settings: LocalRepoSettings | null = local()) => mount(LocalRepoControls, {
  props: { repo: repo('alpha', { local_settings: settings }) },
})
const checked = (wrapper: ReturnType<typeof panel>) => (wrapper.get('[data-test="local-auto-continue"]').element as HTMLInputElement).checked

describe('machine-local repository controls', () => {
  it('keeps on while saving off, then shows only the confirmed off', async () => {
    let resolve!: (value: LocalRepoSettings) => void
    vi.mocked(patchLocalRepoSettings).mockReturnValue(new Promise(r => { resolve = r }))
    const wrapper = panel()
    await wrapper.get('[data-test="local-auto-continue"]').setValue(false)
    expect(checked(wrapper)).toBe(true)
    expect(wrapper.text()).toContain('Ukládání…')
    expect(wrapper.find('[data-test="local-off-note"]').exists()).toBe(false)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeDefined()
    expect(patchLocalRepoSettings).toHaveBeenCalledWith('alpha', { auto_continue: false })
    resolve(local(false))
    await flushPromises()
    expect(checked(wrapper)).toBe(false)
    expect(wrapper.text()).toContain('Uloženo')
    expect(wrapper.text()).toContain('Aktuální běhy doběhnou, další se nespustí')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('keeps confirmed on when an off write fails', async () => {
    vi.mocked(patchLocalRepoSettings).mockRejectedValue(new Error('disk full'))
    const wrapper = panel()
    await wrapper.get('[data-test="local-auto-continue"]').setValue(false)
    await flushPromises()
    expect(checked(wrapper)).toBe(true)
    expect(wrapper.get('[role="alert"]').text()).toContain('disk full')
    expect(wrapper.find('[data-test="local-off-note"]').exists()).toBe(false)
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
  })

  it('shows unavailable settings and harness without a nonfunctional import button', () => {
    const missing = panel(null)
    expect(missing.get('fieldset').attributes('disabled')).toBeDefined()
    expect(missing.get('[role="alert"]').text()).toContain('nejsou')
    const unavailable = panel({ ...local(), effective_harness: 'pi', settings: { ...local().settings, harness: 'pi' } })
    expect(unavailable.text()).toContain('nedostupný')
    expect(unavailable.text()).toContain('pouze pro novou Factory')
    expect(unavailable.find('[data-test="local-import"]').exists()).toBe(false)
    expect(missing.get('[data-test="local-harness"]').attributes('disabled')).toBeDefined()
  })

  it('reports a failed catalog read while keeping automation usable', async () => {
    vi.mocked(fetchHarnessSettings).mockRejectedValueOnce(new Error('catalog offline'))
    const wrapper = panel()
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('catalog offline')
    expect(wrapper.get('[data-test="local-harness"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
  })

  it('keeps the confirmed harness during a keyboard save and after a failed write', async () => {
    let reject!: (reason: Error) => void
    vi.mocked(patchLocalRepoSettings).mockReturnValue(new Promise((_, fail) => { reject = fail }))
    const wrapper = panel()
    await flushPromises()
    const trigger = wrapper.get('[data-test="local-harness"]')
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    await trigger.trigger('keydown', { key: 'End' })
    await trigger.trigger('keydown', { key: 'Enter' })
    expect(patchLocalRepoSettings).toHaveBeenCalledWith('alpha', { harness: 'codex' })
    expect(trigger.attributes('data-value')).toBe('')
    expect(trigger.text()).toContain('Podle počítače')
    expect(trigger.attributes('disabled')).toBeDefined()
    await trigger.trigger('keydown', { key: 'ArrowDown' })
    expect(trigger.attributes('aria-expanded')).toBe('false')
    reject(new Error('disk full'))
    await flushPromises()
    expect(trigger.attributes('data-value')).toBe('')
    expect(trigger.attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[role="alert"]').text()).toContain('disk full')
  })

  it('shows an unavailable saved harness without offering it for selection', async () => {
    const wrapper = panel({ ...local(), effective_harness: 'pi', settings: { ...local().settings, harness: 'pi' } })
    await flushPromises()
    expect(wrapper.get('[data-test="local-harness"]').text()).toContain('pi (nedostupný)')
    expect(await selectLabels(wrapper, '[data-test="local-harness"]')).toEqual(['Podle počítače (codex)', 'codex'])
  })

  it('patches harness only and accepts updated values from another tab', async () => {
    vi.mocked(patchLocalRepoSettings).mockResolvedValue({ ...local(), settings: { ...local().settings, harness: 'codex' } })
    const wrapper = panel()
    await flushPromises()
    await chooseOption(wrapper, '[data-test="local-harness"]', 'codex')
    await flushPromises()
    expect(patchLocalRepoSettings).toHaveBeenCalledWith('alpha', { harness: 'codex' })
    await wrapper.setProps({ repo: repo('alpha', { local_settings: local(false) }) })
    expect(checked(wrapper)).toBe(false)
    expect(wrapper.get('[data-test="local-harness"]').attributes('aria-label')).toBe('Výchozí harness')
  })
})
