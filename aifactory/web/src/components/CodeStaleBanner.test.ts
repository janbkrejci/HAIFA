import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CodeStaleBanner from './CodeStaleBanner.vue'

describe('CodeStaleBanner', () => {
  it('renders nothing while the code is current', () => {
    const wrapper = mount(CodeStaleBanner, { props: { stale: false, restarting: false, error: null } })
    expect(wrapper.find('[data-test="code-banner"]').exists()).toBe(false)
  })

  it('asks for a restart and emits it on click', async () => {
    const wrapper = mount(CodeStaleBanner, { props: { stale: true, restarting: false, error: null } })
    const banner = wrapper.get('[data-test="code-banner"]')
    expect(banner.attributes('role')).toBe('alert')
    expect(banner.text()).toContain('Zápisy jsou vypnuté')
    await wrapper.get('[data-test="code-restart"]').trigger('click')
    expect(wrapper.emitted('restart')).toHaveLength(1)
  })

  it('spins and disables the button while restarting', () => {
    const wrapper = mount(CodeStaleBanner, { props: { stale: true, restarting: true, error: null } })
    const button = wrapper.get('[data-test="code-restart"]')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.find('[data-test="spinner"]').exists()).toBe(true)
    expect(button.text()).toContain('Restartuji')
  })

  it('shows a failed restart', () => {
    const wrapper = mount(CodeStaleBanner, {
      props: { stale: true, restarting: false, error: 'Dashboard se do minuty nerestartoval.' },
    })
    expect(wrapper.get('[data-test="code-error"]').text()).toContain('nerestartoval')
  })
})
