import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { h } from 'vue'
import Tooltip from './Tooltip.vue'

let wrapper: VueWrapper | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

function tip(): HTMLElement | null {
  return document.body.querySelector<HTMLElement>('[data-test="tooltip"]')
}

function wrap() {
  wrapper = mount(Tooltip, {
    props: { text: 'Nápověda' },
    slots: { default: () => h('button', { type: 'button', class: 'target' }, 'cíl') },
    attachTo: document.body,
  })
  return wrapper
}

describe('Tooltip', () => {
  it('shows on hover and hides on leave', async () => {
    const w = wrap()
    expect(tip()).toBeNull()
    await w.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    expect(tip()?.getAttribute('role')).toBe('tooltip')
    expect(tip()?.textContent?.trim()).toBe('Nápověda')
    expect(tip()?.parentElement).toBe(document.body)
    expect(w.find('[data-test="tip-anchor"]').attributes('aria-describedby')).toBe(tip()?.id)
    await w.find('[data-test="tip-anchor"]').trigger('mouseleave')
    expect(tip()).toBeNull()
  })

  it('shows on keyboard focus, hides on blur and Escape', async () => {
    const w = wrap()
    await w.find('.target').trigger('focusin')
    expect(tip()).not.toBeNull()
    await w.find('.target').trigger('focusout')
    expect(tip()).toBeNull()
    await w.find('.target').trigger('focusin')
    await w.find('.target').trigger('keydown', { key: 'Escape' })
    expect(tip()).toBeNull()
  })

  it('follows a controlled anchor outside of any container', async () => {
    const node = document.createElement('div')
    document.body.appendChild(node)
    wrapper = mount(Tooltip, { props: { text: 'Uzel', anchor: null }, attachTo: document.body })
    expect(tip()).toBeNull()
    expect(wrapper.find('[data-test="tip-anchor"]').exists()).toBe(false)
    await wrapper.setProps({ anchor: node })
    await flushPromises()
    expect(tip()?.textContent?.trim()).toBe('Uzel')
    expect(tip()?.parentElement).toBe(document.body)
    await wrapper.setProps({ anchor: null })
    expect(tip()).toBeNull()
  })
})
