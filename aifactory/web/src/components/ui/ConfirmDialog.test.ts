import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ConfirmDialog from './ConfirmDialog.vue'

let wrapper: VueWrapper | null = null
let outside: HTMLButtonElement | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  outside?.remove()
  outside = null
})

function q<T extends HTMLElement = HTMLElement>(test: string): T | null {
  return document.body.querySelector<T>(`[data-test="${test}"]`)
}

function key(el: Element, k: string, shiftKey = false) {
  el.dispatchEvent(new KeyboardEvent('keydown', { key: k, shiftKey, bubbles: true, cancelable: true }))
}

async function open(props: Record<string, unknown> = {}) {
  wrapper = mount(ConfirmDialog, {
    props: { open: true, title: 'Opravdu?', message: 'Řádek 1\nŘádek 2', ...props },
    attachTo: document.body,
  })
  await flushPromises()
  return wrapper
}

describe('ConfirmDialog', () => {
  it('renders nothing while closed', async () => {
    await open({ open: false })
    expect(q('confirm-dialog')).toBeNull()
  })

  it('renders a labelled modal in <body> with Potvrdit and Zrušit', async () => {
    await open()
    const dialog = q('confirm-dialog')!
    expect(dialog.getAttribute('role')).toBe('dialog')
    expect(dialog.hasAttribute('title')).toBe(false)
    expect(dialog.querySelector('[title]')).toBeNull()
    expect(dialog.getAttribute('aria-modal')).toBe('true')
    expect(document.getElementById(dialog.getAttribute('aria-labelledby')!)?.textContent).toBe('Opravdu?')
    expect(q('confirm-message')?.textContent).toBe('Řádek 1\nŘádek 2')
    expect(q('confirm-ok')?.textContent?.trim()).toBe('Potvrdit')
    expect(q('confirm-cancel')?.textContent?.trim()).toBe('Zrušit')
    expect(q('confirm-backdrop')?.parentElement).toBe(document.body)
  })

  it('emits confirm and cancel from the buttons', async () => {
    const w = await open()
    q('confirm-ok')!.click()
    q('confirm-cancel')!.click()
    expect(w.emitted('confirm')).toHaveLength(1)
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('keeps a blocked plan unconfirmable by button and keyboard', async () => {
    const w = await open({ confirmDisabled: true })
    expect(q<HTMLButtonElement>('confirm-ok')!.disabled).toBe(true)
    expect(document.activeElement).toBe(q('confirm-cancel'))
    key(q('confirm-dialog')!, 'Enter')
    q('confirm-ok')!.click()
    expect(w.emitted('confirm')).toBeUndefined()
  })

  it('cancels on Escape and confirms on Enter', async () => {
    const w = await open()
    key(q('confirm-dialog')!, 'Escape')
    expect(w.emitted('cancel')).toHaveLength(1)
    key(q('confirm-ok')!, 'Enter')
    expect(w.emitted('confirm')).toHaveLength(1)
  })

  it('cancels on a click outside the panel only', async () => {
    const w = await open()
    q('confirm-dialog')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(w.emitted('cancel')).toBeUndefined()
    q('confirm-backdrop')!.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    expect(w.emitted('cancel')).toHaveLength(1)
  })

  it('keeps focus inside and returns it to the opener', async () => {
    outside = document.createElement('button')
    document.body.appendChild(outside)
    outside.focus()
    const w = await open({ open: false })
    await w.setProps({ open: true })
    await flushPromises()
    expect(document.activeElement).toBe(q('confirm-ok'))
    key(q('confirm-ok')!, 'Tab')
    expect(document.activeElement).toBe(q('confirm-cancel'))
    key(q('confirm-cancel')!, 'Tab', true)
    expect(document.activeElement).toBe(q('confirm-ok'))
    await w.setProps({ open: false })
    await flushPromises()
    expect(q('confirm-dialog')).toBeNull()
    expect(document.activeElement).toBe(outside)
  })
})
