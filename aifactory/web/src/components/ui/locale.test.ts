import { afterEach, expect, it } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { setLocale } from '@/lib/i18n'
import ConfirmDialog from './ConfirmDialog.vue'
import ModelPickerDialog from './ModelPickerDialog.vue'
import CodePickerDialog from './CodePickerDialog.vue'
import MarkdownView from './MarkdownView.vue'
import AsyncLoadState from './AsyncLoadState.vue'

enableAutoUnmount(afterEach)
afterEach(() => setLocale('en'))

it('updates default confirmation buttons while preserving slotted input and the open dialog', async () => {
  setLocale('en')
  mount(ConfirmDialog, { props: { open: true, title: 'User title' }, slots: { default: '<input value="user draft">' } })
  await flushPromises()
  const dialog = document.body.querySelector('[role="dialog"]')!
  const input = dialog.querySelector('input')!
  expect(dialog.textContent).toContain('Confirm')
  setLocale('cs')
  await nextTick()
  expect(dialog.textContent).toContain('Potvrdit')
  expect(dialog.textContent).toContain('Zrušit')
  expect(dialog.querySelector('input')).toBe(input)
  expect(input.value).toBe('user draft')
})

it('keeps the model filter and selection while translating the open picker', async () => {
  setLocale('en')
  const wrapper = mount(ModelPickerDialog, { props: { open: true, harness: 'codex', models: ['gpt-a', 'gpt-b'], model: 'gpt-a' } })
  await flushPromises()
  const input = document.body.querySelector<HTMLInputElement>('[data-test="model-picker-search"]')!
  input.value = 'gpt-b'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  const option = document.body.querySelector<HTMLButtonElement>('[data-model="gpt-b"]')!
  option.click()
  await nextTick()
  expect(document.body.textContent).toContain('1 of 2 models')
  setLocale('cs')
  await nextTick()
  expect(input.placeholder).toBe('Filtrovat modely…')
  expect(input.value).toBe('gpt-b')
  expect(option.getAttribute('aria-selected')).toBe('true')
  expect(document.body.textContent).toContain('1 z 2 modelů')
  document.body.querySelector<HTMLButtonElement>('[data-test="confirm-ok"]')!.click()
  expect(wrapper.emitted('choose')).toEqual([['gpt-b']])
})

it('updates code search accessibility labels and keeps the query', async () => {
  setLocale('en')
  mount(CodePickerDialog, { props: { open: true, heading: 'User heading', options: [{ value: 'P01', label: 'P01 · Český název' }] } })
  await flushPromises()
  const input = document.body.querySelector<HTMLInputElement>('[data-test="code-picker-search"]')!
  expect(input.getAttribute('aria-label')).toBe('Search by code or name')
  input.value = 'Český'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  await nextTick()
  setLocale('cs')
  await nextTick()
  expect(input.getAttribute('aria-label')).toBe('Hledat podle kódu nebo názvu')
  expect(input.value).toBe('Český')
  expect(document.body.textContent).toContain('Český název')
})

it('keeps the markdown source tab and user content through a round trip', async () => {
  setLocale('en')
  const wrapper = mount(MarkdownView, { props: { source: '# Český text' } })
  await wrapper.get('[data-test="md-tab-source"]').trigger('click')
  for (const language of ['cs', 'en'] as const) {
    setLocale(language)
    await nextTick()
    expect(wrapper.get('[data-test="md-tab-source"]').text()).toBe(language === 'cs' ? 'Zdroj' : 'Source')
    expect(wrapper.get('[data-test="md-source"]').text()).toBe('# Český text')
  }
})

it('translates loading and recovery states in place', async () => {
  setLocale('en')
  const wrapper = mount(AsyncLoadState)
  expect(wrapper.text()).toBe('Loading…')
  setLocale('cs')
  await nextTick()
  expect(wrapper.text()).toBe('Načítám…')
  await wrapper.setProps({ error: new Error('chunk failed') })
  expect(wrapper.text()).toContain('Obrazovku se nepodařilo načíst.')
  setLocale('en')
  await nextTick()
  expect(wrapper.get('button').text()).toBe('Reload')
  expect(wrapper.text()).toContain('Could not load the screen.')
})
