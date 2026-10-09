import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import Spinner from './Spinner.vue'

describe('Spinner', () => {
  it('renders the shared spinner with its size', () => {
    const wrapper = mount(Spinner, { props: { size: 20 } })
    const el = wrapper.find('[data-test="spinner"]')
    expect(el.exists()).toBe(true)
    expect(el.classes()).toContain('spinner')
    expect(el.attributes('aria-hidden')).toBe('true')
    expect(el.attributes('style')).toContain('width: 20px')
    expect(mount(Spinner).find('.spinner').attributes('style')).toContain('height: 14px')
  })
})
