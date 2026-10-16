import { afterEach, describe, expect, it } from 'vitest'
import { enableAutoUnmount, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import CollapsibleSection from './CollapsibleSection.vue'

enableAutoUnmount(afterEach)
afterEach(() => { document.body.innerHTML = '' })

const mountSection = (props: Record<string, unknown> = {}) => mount(CollapsibleSection, {
  props: { heading: 'Nastavení agentů', ...props },
  slots: { default: '<p data-test="content">obsah</p>', aside: '<span data-test="aside">Uloženo</span>' },
  attachTo: document.body,
})

describe('CollapsibleSection', () => {
  it('is an h2 with a button that collapses and expands the content and reports its state', async () => {
    const w = mountSection()
    const toggle = w.get('h2 > button')
    expect(w.get('h2').text()).toBe('Nastavení agentů')
    expect(toggle.attributes('type')).toBe('button')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    const body = w.get('[data-test="section-body"]')
    expect(toggle.attributes('aria-controls')).toBe(body.attributes('id'))
    expect(w.get('[data-test="content"]').isVisible()).toBe(true)
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(w.get('[data-test="content"]').isVisible()).toBe(false)
    // the content stays mounted, so its state survives collapsing
    expect(w.find('[data-test="content"]').exists()).toBe(true)
    // the aside stays visible next to the heading
    expect(w.get('[data-test="aside"]').isVisible()).toBe(true)
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(w.get('[data-test="content"]').isVisible()).toBe(true)
  })

  it('is reachable from the keyboard: a native button activated by Enter and Space', () => {
    const w = mountSection()
    const toggle = w.get('[data-test="section-toggle"]').element as HTMLButtonElement
    toggle.focus()
    expect(document.activeElement).toBe(toggle)
    expect(toggle.tagName).toBe('BUTTON')
    expect(toggle.disabled).toBe(false)
  })

  it('follows v-model:open, so the page can open a collapsed section', async () => {
    const w = mountSection({ open: false })
    expect(w.get('[data-test="content"]').isVisible()).toBe(false)
    await w.get('[data-test="section-toggle"]').trigger('click')
    expect(w.emitted('update:open')).toEqual([[true]])
    await w.setProps({ open: true })
    await nextTick()
    expect(w.get('[data-test="content"]').isVisible()).toBe(true)
  })
})
