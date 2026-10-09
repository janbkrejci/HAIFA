import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { h } from 'vue'
import CodeTip from './CodeTip.vue'
import { mergeNames, resetNamesForTests } from '@/lib/names'

let wrapper: VueWrapper | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  resetNamesForTests()
  document.body.innerHTML = ''
})

function tip(): string | null {
  return document.body.querySelector('[data-test="tooltip"]')?.textContent?.trim() ?? null
}

describe('CodeTip', () => {
  it('shows the title and level of the code and follows a rename', async () => {
    mergeNames({ 'M01-S01': { title: 'Model', level: 'step' } })
    wrapper = mount(CodeTip, { props: { code: 'M01-S01' }, attachTo: document.body })
    expect(wrapper.text()).toBe('M01-S01')
    expect(wrapper.find('[title]').exists()).toBe(false)
    await wrapper.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    expect(tip()).toBe('Step: Model')
    mergeNames({ 'M01-S01': { title: 'Model v2', level: 'step' } })
    await flushPromises()
    expect(tip()).toBe('Step: Model v2')
  })

  it('wraps its slot and shows nothing for an unknown code', async () => {
    wrapper = mount(CodeTip, {
      props: { code: 'X99' },
      slots: { default: () => h('a', { class: 'link', href: '#' }, 'X99') },
      attachTo: document.body,
    })
    expect(wrapper.find('a.link').text()).toBe('X99')
    await wrapper.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    expect(tip()).toBeNull()
  })
})
