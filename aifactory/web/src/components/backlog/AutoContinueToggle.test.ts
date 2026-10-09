import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import AutoContinueToggle from './AutoContinueToggle.vue'

describe('AutoContinueToggle', () => {
  it('highlights the current mode and emits a change', async () => {
    const wrapper = mount(AutoContinueToggle, {
      props: { mode: 'inherit', effective: true, busy: false },
    })
    expect(wrapper.find('[data-test="auto-inherit"]').classes()).toContain('active')
    expect(wrapper.find('[data-test="auto-on"]').classes()).not.toContain('active')
    expect(wrapper.find('[data-test="auto-effective"]').text()).toBe('efektivně: zapnuto')
    await wrapper.find('[data-test="auto-on"]').trigger('click')
    await wrapper.find('[data-test="auto-off"]').trigger('click')
    await wrapper.find('[data-test="auto-inherit"]').trigger('click')
    expect(wrapper.emitted('change')).toEqual([['on'], ['off']])
  })

  it('renders the auto-merge switch with its own label and test ids', async () => {
    const wrapper = mount(AutoContinueToggle, {
      props: {
        mode: 'on',
        effective: true,
        busy: false,
        label: 'Auto-merge',
        testPrefix: 'merge',
        hint: 'workflow bez review se automaticky nemerguje',
      },
    })
    expect(wrapper.find('[data-test="merge-toggle"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="auto-toggle"]').exists()).toBe(false)
    expect(wrapper.find('[role="group"]').attributes('aria-label')).toBe('Auto-merge')
    expect(wrapper.find('[data-test="merge-on"]').classes()).toContain('active')
    expect(wrapper.find('[data-test="merge-effective"]').text()).toBe('efektivně: zapnuto')
    expect(wrapper.find('[data-test="merge-hint"]').text()).toContain('bez review')
    await wrapper.find('[data-test="merge-off"]').trigger('click')
    expect(wrapper.emitted('change')).toEqual([['off']])
  })

  it('is disabled while busy', () => {
    const wrapper = mount(AutoContinueToggle, {
      props: { mode: 'off', effective: false, busy: true },
    })
    expect(wrapper.find('[data-test="auto-on"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="auto-effective"]').text()).toBe('efektivně: vypnuto')
  })
})
