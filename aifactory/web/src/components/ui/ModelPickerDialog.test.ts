import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ModelPickerDialog from './ModelPickerDialog.vue'

let wrapper: VueWrapper | null = null
afterEach(() => { wrapper?.unmount(); wrapper = null })
function q(test: string) { return document.body.querySelector<HTMLElement>(`[data-test="${test}"]`)! }
describe('ModelPickerDialog', () => {
  it('filters case-insensitively, selects a model and confirms it', async () => {
    wrapper = mount(ModelPickerDialog, { props: { open: true, harness: 'claude', models: ['opus', 'sonnet', 'haiku'], model: 'opus' }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement).toBe(q('model-picker-search'))
    const input = q('model-picker-search') as HTMLInputElement
    input.value = 'SON'; input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    const options = document.body.querySelectorAll<HTMLElement>('[role="option"]')
    expect(options).toHaveLength(1)
    options[0]!.click()
    await flushPromises()
    q('confirm-ok').click()
    expect(wrapper.emitted('choose')).toEqual([['sonnet']])
  })
  it('shows an empty filter result and lets Escape cancel', async () => {
    wrapper = mount(ModelPickerDialog, { props: { open: true, harness: 'codex', models: ['gpt-5'], model: 'gpt-5' }, attachTo: document.body })
    await flushPromises()
    const input = q('model-picker-search') as HTMLInputElement
    input.value = 'missing'; input.dispatchEvent(new Event('input', { bubbles: true }))
    await flushPromises()
    expect(q('model-picker-list').textContent).toContain('Žádný model')
    expect(q('confirm-ok').hasAttribute('disabled')).toBe(true)
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('choose')).toBeUndefined()
  })
})
