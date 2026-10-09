import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BackLink from './BackLink.vue'

describe('BackLink', () => {
  it('renders an arrow icon and the label', () => {
    const wrapper = mount(BackLink, { props: { href: '#/runs', label: 'všechny běhy' } })
    const link = wrapper.find('a[data-test="back"]')
    expect(link.attributes('href')).toBe('#/runs')
    expect(link.find('svg').exists()).toBe(true)
    expect(link.find('svg').attributes('aria-hidden')).toBe('true')
    expect(link.text()).toBe('všechny běhy')
    expect(link.text()).not.toContain('←')
  })
})
