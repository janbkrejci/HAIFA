import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import CodePickerDialog from './CodePickerDialog.vue'

let wrapper: VueWrapper | null = null
afterEach(() => { wrapper?.unmount(); wrapper = null })
function q(test: string) { return document.body.querySelector<HTMLElement>(`[data-test="${test}"]`)! }
function codes() { return Array.from(document.body.querySelectorAll<HTMLElement>('[role="option"]')).map((o) => o.dataset.value) }
async function type(text: string) {
  const input = q('code-picker-search') as HTMLInputElement
  input.value = text; input.dispatchEvent(new Event('input', { bubbles: true }))
  await flushPromises()
}
const options = [
  { value: 'M01-S01-T01', label: 'M01-S01-T01 · Schéma' },
  { value: 'M01-S01-T02', label: 'M01-S01-T02 · Loader' },
  { value: 'M02-S01-T01', label: 'M02-S01-T01 · Filtr' },
]

describe('CodePickerDialog', () => {
  it('filters by code and by title and confirms the selection', async () => {
    wrapper = mount(CodePickerDialog, { props: { open: true, heading: 'Závisí na', options }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement).toBe(q('code-picker-search'))
    await type('m02')
    expect(codes()).toEqual(['M02-S01-T01'])
    await type('LOAD')
    expect(codes()).toEqual(['M01-S01-T02'])
    q('confirm-ok').click()
    expect(wrapper.emitted('choose')).toEqual([['M01-S01-T02']])
  })

  it('picks a code with a single click', async () => {
    wrapper = mount(CodePickerDialog, { props: { open: true, heading: 'Závisí na', options }, attachTo: document.body })
    await flushPromises()
    document.body.querySelector<HTMLElement>('[role="option"][data-value="M01-S01-T01"]')!.click()
    expect(wrapper.emitted('choose')).toEqual([['M01-S01-T01']])
  })

  it('moves the selection with the keyboard and picks it with Enter', async () => {
    wrapper = mount(CodePickerDialog, { props: { open: true, heading: 'Závisí na', options }, attachTo: document.body })
    await flushPromises()
    const input = q('code-picker-search')
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true }))
    await flushPromises()
    q('select-list').dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true, cancelable: true }))
    await flushPromises()
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('choose')).toEqual([['M02-S01-T01']])
  })

  it('shows an empty result and closes on Escape without a choice', async () => {
    wrapper = mount(CodePickerDialog, { props: { open: true, heading: 'Závisí na', options }, attachTo: document.body })
    await flushPromises()
    await type('nic takového')
    expect(q('select-list').textContent).toContain('Nic neodpovídá')
    expect(q('confirm-ok').hasAttribute('disabled')).toBe(true)
    q('code-picker-search').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    expect(wrapper.emitted('choose')).toBeUndefined()
  })
})
