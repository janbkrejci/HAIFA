import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import MachineHarnessesDialog from './MachineHarnessesDialog.vue'
import { fetchHarnessSettings, saveHarnessSettings, testHarness } from '@/lib/machineHarnesses'

vi.mock('@/lib/machineHarnesses', () => ({ fetchHarnessSettings: vi.fn(), saveHarnessSettings: vi.fn(), testHarness: vi.fn() }))
let wrapper: VueWrapper | null = null
afterEach(() => { wrapper?.unmount(); wrapper = null; vi.clearAllMocks() })

const settings = {
  version: 1, default_harness: 'codex',
  harnesses: {
    claude: { enabled: true, model: 'sonnet', thinking: 'high' },
    codex: { enabled: true, model: 'gpt-5.5', thinking: 'medium' },
    pi: { enabled: false, model: '' },
  },
}
async function open() {
  vi.mocked(fetchHarnessSettings).mockResolvedValue({
    settings: structuredClone(settings), available: { claude: true, codex: true, pi: false },
    models: { claude: ['sonnet', 'opus'], codex: ['gpt-5.5', 'gpt-5'], pi: [] }, configured: true,
    thinking_levels: { claude: { sonnet: ['low', 'medium', 'high', 'max'], opus: ['low', 'medium', 'high', 'max'] }, codex: { 'gpt-5.5': ['low', 'medium', 'high', 'xhigh'], 'gpt-5': ['low', 'medium', 'high'] } },
    thinking_defaults: { claude: { sonnet: 'high', opus: 'medium' }, codex: { 'gpt-5.5': 'medium', 'gpt-5': 'medium' } },
  })
  wrapper = mount(MachineHarnessesDialog, { props: { open: true }, attachTo: document.body })
  await flushPromises()
  return wrapper
}
function el(test: string) { return document.body.querySelector<HTMLElement>(`[data-test="${test}"]`)! }

describe('MachineHarnessesDialog', () => {
  it('blocks a failed default model and enables it again after a successful test', async () => {
    const w = await open()
    vi.mocked(testHarness).mockResolvedValueOnce({ ok: false, error: 'Login failed' })
    el('machine-test-codex').click()
    await flushPromises()
    expect(testHarness).toHaveBeenCalledWith('codex', 'gpt-5.5', 'medium')
    expect(el('machine-test-result-codex').textContent).toContain('Login failed')
    expect(el('machine-default-codex').hasAttribute('disabled')).toBe(true)
    expect((el('machine-default-claude') as HTMLInputElement).checked).toBe(true)
    vi.mocked(testHarness).mockResolvedValueOnce({ ok: true, answer: 'OK' })
    el('machine-test-codex').click()
    await flushPromises()
    expect(el('machine-default-codex').hasAttribute('disabled')).toBe(false)
    expect(w.emitted('tested')).toHaveLength(2)
    expect(w.emitted('close')).toBeUndefined()
  })
  it('lists installed harnesses, saves choices and moves the default when disabled', async () => {
    const w = await open()
    expect(el('machine-enabled-pi').hasAttribute('disabled')).toBe(true)
    el('machine-enabled-codex').click()
    await flushPromises()
    expect((el('machine-default-claude') as HTMLInputElement).checked).toBe(true)
    el('machine-model-claude').click()
    await flushPromises()
    const opus = Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]')).find(e => e.textContent?.trim() === 'opus')!
    opus.click()
    await flushPromises()
    el('confirm-ok').click()
    await flushPromises()
    el('confirm-ok').click()
    await flushPromises()
    expect(saveHarnessSettings).toHaveBeenCalledWith({ ...settings, default_harness: 'claude', harnesses: {
      claude: { enabled: true, model: 'opus', thinking: 'high' }, codex: { enabled: false, model: 'gpt-5.5', thinking: 'medium' }, pi: { enabled: false, model: '' },
    } })
    expect(w.emitted('saved')).toHaveLength(1)
    expect(w.emitted('close')).toHaveLength(1)
  })
  it('keeps failed saves visible for correction', async () => {
    const w = await open()
    vi.mocked(saveHarnessSettings).mockRejectedValueOnce(new Error('Nelze uložit'))
    el('confirm-ok').click()
    await flushPromises()
    expect(el('machine-harness-error').textContent).toContain('Nelze uložit')
    expect(w.emitted('close')).toBeUndefined()
  })
  it('offers model-specific thinking, tests it and resets unsupported levels on model change', async () => {
    await open()
    const thinking = el('machine-thinking-codex')
    thinking.click()
    await flushPromises()
    expect(document.body.querySelector('[data-test="select-list"]')?.textContent).not.toContain('max')
    expect(document.body.querySelector('[data-test="select-list"]')?.textContent).not.toContain('Použít nastavení agenta')
    expect(document.body.querySelector('[data-test="select-list"]')?.textContent).not.toContain('Vypnuto')
    thinking.dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true, cancelable: true }))
    thinking.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    await flushPromises()
    expect(thinking.dataset.value).toBe('xhigh')
    vi.mocked(testHarness).mockResolvedValueOnce({ ok: true, answer: 'OK' })
    el('machine-test-codex').click()
    await flushPromises()
    expect(testHarness).toHaveBeenCalledWith('codex', 'gpt-5.5', 'xhigh')
    el('machine-model-codex').click()
    await flushPromises()
    Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]')).find(e => e.textContent?.trim() === 'gpt-5')!.click()
    await flushPromises()
    el('confirm-ok').click()
    await flushPromises()
    expect(el('machine-thinking-codex').dataset.value).toBe('medium')
    el('confirm-ok').click()
    await flushPromises()
    expect(vi.mocked(saveHarnessSettings).mock.calls[0]![0].harnesses.codex!.thinking).toBe('medium')
  })
})
