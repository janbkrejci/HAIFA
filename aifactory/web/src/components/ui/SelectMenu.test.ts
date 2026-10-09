import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import SelectMenu from './SelectMenu.vue'
import type { SelectOption } from '@/lib/select'

const OPTIONS: SelectOption[] = [
  { value: '', label: 'vše' },
  { value: 'todo', label: 'todo' },
  { value: 'running', label: 'běží' },
  { value: 'blocked', label: 'blokováno' },
  { value: 'cancelled', label: 'cancelled' },
  { value: 'done', label: 'hotovo' },
]

let wrapper: VueWrapper | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
  vi.useRealTimers()
})

function mountSelect(props: Partial<InstanceType<typeof SelectMenu>['$props']> = {}) {
  const w: VueWrapper = mount(SelectMenu, {
    props: {
      modelValue: 'todo',
      options: OPTIONS,
      label: 'Stav',
      'onUpdate:modelValue': (value: string) => w.setProps({ modelValue: value }),
      ...props,
    },
    attrs: { 'data-test': 'pick' },
    attachTo: document.body,
  })
  wrapper = w
  return w
}

function trigger(w: VueWrapper) {
  return w.get('[data-test="pick"]')
}

function list(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>('[data-test="select-list"]')
}

function option(value: string): HTMLElement {
  const el = list()?.querySelector<HTMLElement>(`[role="option"][data-value="${value}"]`)
  if (!el) throw new Error(`no option ${value}`)
  return el
}

function activeValue(w: VueWrapper): string | undefined {
  const id = trigger(w).attributes('aria-activedescendant')
  return id ? document.getElementById(id)?.dataset.value : undefined
}

async function key(w: VueWrapper, k: string, init: KeyboardEventInit = {}) {
  await trigger(w).trigger('keydown', { key: k, ...init })
  await flushPromises()
}

function emitted(w: VueWrapper): string[] {
  return (w.emitted('update:modelValue') ?? []).map((args) => args[0] as string)
}

describe('SelectMenu', () => {
  it('renders an accessible trigger with the selected label', () => {
    const w = mountSelect()
    const t = trigger(w)
    expect(t.element.tagName).toBe('BUTTON')
    expect(t.attributes('type')).toBe('button')
    expect(t.attributes('role')).toBe('combobox')
    expect(t.attributes('aria-haspopup')).toBe('listbox')
    expect(t.attributes('aria-label')).toBe('Stav')
    expect(t.attributes('aria-expanded')).toBe('false')
    expect(t.attributes('data-value')).toBe('todo')
    expect(t.text()).toBe('todo')
    expect(t.attributes('title')).toBeUndefined()
    expect(document.querySelector('select')).toBeNull()
    expect(list()).toBeNull()
  })

  it('opens on click, in <body>, and picks an option with the mouse', async () => {
    const w = mountSelect()
    await trigger(w).trigger('click')
    await flushPromises()
    const l = list()
    expect(l?.parentElement).toBe(document.body)
    expect(l?.getAttribute('role')).toBe('listbox')
    expect(trigger(w).attributes('aria-expanded')).toBe('true')
    expect(trigger(w).attributes('aria-controls')).toBe(l?.id)
    expect([...l!.querySelectorAll('[role="option"]')].map((o) => o.textContent?.trim())).toEqual(
      OPTIONS.map((o) => o.label),
    )
    expect(option('todo').getAttribute('aria-selected')).toBe('true')
    expect(option('blocked').getAttribute('aria-selected')).toBe('false')
    option('blocked').dispatchEvent(new MouseEvent('mousemove', { bubbles: true }))
    await flushPromises()
    expect(option('blocked').classList).toContain('active')
    option('blocked').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(emitted(w)).toEqual(['blocked'])
    expect(list()).toBeNull()
    expect(trigger(w).attributes('aria-expanded')).toBe('false')
    expect(trigger(w).text()).toBe('blokováno')
    expect(document.activeElement).toBe(trigger(w).element)
  })

  it('toggles closed on a second click and ignores the already selected option', async () => {
    const w = mountSelect()
    await trigger(w).trigger('click')
    await trigger(w).trigger('click')
    expect(list()).toBeNull()
    await trigger(w).trigger('click')
    await flushPromises()
    option('todo').dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(emitted(w)).toEqual([])
    expect(list()).toBeNull()
  })

  it('closes on a click outside, not on a click inside the list', async () => {
    const w = mountSelect()
    await trigger(w).trigger('click')
    await flushPromises()
    list()!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(list()).not.toBeNull()
    document.body.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    await flushPromises()
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual([])
  })

  it('closes when the page scrolls, but not when the list itself scrolls', async () => {
    const w = mountSelect()
    await trigger(w).trigger('click')
    await flushPromises()
    list()!.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(list()).not.toBeNull()
    document.dispatchEvent(new Event('scroll'))
    await flushPromises()
    expect(list()).toBeNull()
    await trigger(w).trigger('click')
    window.dispatchEvent(new Event('resize'))
    await flushPromises()
    expect(list()).toBeNull()
  })

  it('works with the arrows, Home/End, Enter and Escape', async () => {
    const w = mountSelect()
    await key(w, 'ArrowDown')
    expect(list()).not.toBeNull()
    expect(activeValue(w)).toBe('todo')
    await key(w, 'ArrowDown')
    expect(activeValue(w)).toBe('running')
    await key(w, 'ArrowUp')
    await key(w, 'ArrowUp')
    expect(activeValue(w)).toBe('')
    await key(w, 'ArrowUp')
    expect(activeValue(w)).toBe('')
    await key(w, 'End')
    expect(activeValue(w)).toBe('done')
    await key(w, 'ArrowDown')
    expect(activeValue(w)).toBe('done')
    await key(w, 'Home')
    expect(activeValue(w)).toBe('')
    await key(w, 'ArrowDown')
    await key(w, 'ArrowDown')
    await key(w, 'ArrowDown')
    await key(w, 'Escape')
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual([])
    await key(w, 'Enter')
    expect(list()).not.toBeNull()
    await key(w, 'ArrowDown')
    await key(w, 'Enter')
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual(['running'])
    expect(trigger(w).text()).toBe('běží')
  })

  it('does not submit a form or close a dialog with Enter and Escape', async () => {
    const w = mountSelect()
    const enter = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    trigger(w).element.dispatchEvent(enter)
    expect(enter.defaultPrevented).toBe(true)
    await flushPromises()
    const outer = vi.fn()
    document.body.addEventListener('keydown', outer)
    const esc = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    trigger(w).element.dispatchEvent(esc)
    expect(esc.defaultPrevented).toBe(true)
    expect(outer).not.toHaveBeenCalled()
    document.body.removeEventListener('keydown', outer)
  })

  it('opens with Space and picks the active option with Tab', async () => {
    const w = mountSelect()
    await key(w, ' ')
    expect(list()).not.toBeNull()
    await key(w, 'ArrowDown')
    const tab = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
    trigger(w).element.dispatchEvent(tab)
    await flushPromises()
    expect(tab.defaultPrevented).toBe(false)
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual(['running'])
  })

  it('jumps to an option by its first letters while open', async () => {
    vi.useFakeTimers()
    const w = mountSelect({ modelValue: '' })
    await key(w, 'ArrowDown')
    await key(w, 'b')
    expect(activeValue(w)).toBe('running')
    await key(w, 'b')
    expect(activeValue(w)).toBe('blocked')
    await key(w, 'b')
    expect(activeValue(w)).toBe('running')
    vi.advanceTimersByTime(600)
    await key(w, 'b')
    await key(w, 'l')
    expect(activeValue(w)).toBe('blocked')
    vi.advanceTimersByTime(600)
    await key(w, 'H')
    expect(activeValue(w)).toBe('done')
    expect(emitted(w)).toEqual([])
    expect(list()).not.toBeNull()
  })

  it('selects by the first letter while closed, like a native select', async () => {
    const w = mountSelect()
    await key(w, 'c')
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual(['cancelled'])
    expect(trigger(w).text()).toBe('cancelled')
    await key(w, 'x')
    expect(emitted(w)).toEqual(['cancelled'])
  })

  it('follows the bound value and shows the placeholder for an unknown one', async () => {
    const w = mountSelect({ placeholder: 'vyber' })
    await w.setProps({ modelValue: 'done' })
    expect(trigger(w).text()).toBe('hotovo')
    expect(trigger(w).attributes('data-value')).toBe('done')
    await w.setProps({ modelValue: 'nope' })
    expect(trigger(w).text()).toBe('vyber')
    expect(trigger(w).find('.select-value').classes()).toContain('faint')
  })

  it('cannot be opened or changed while disabled', async () => {
    const w = mountSelect({ disabled: true })
    expect(trigger(w).attributes('disabled')).toBeDefined()
    await trigger(w).trigger('click')
    await key(w, 'ArrowDown')
    await key(w, 'c')
    expect(list()).toBeNull()
    expect(emitted(w)).toEqual([])
  })

  it('closes when it becomes disabled', async () => {
    const w = mountSelect()
    await trigger(w).trigger('click')
    await flushPromises()
    await w.setProps({ disabled: true })
    expect(list()).toBeNull()
  })

  it('marks an invalid field', async () => {
    const w = mountSelect()
    expect(trigger(w).attributes('aria-invalid')).toBeUndefined()
    await w.setProps({ invalid: true })
    expect(trigger(w).attributes('aria-invalid')).toBe('true')
    expect(trigger(w).classes()).toContain('invalid')
  })
})
