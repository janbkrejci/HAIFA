import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import MarkdownView from './MarkdownView.vue'

const SOURCE = '## Zadání\n\nText <!-- skryté -->\n'

describe('MarkdownView', () => {
  it('starts in preview', () => {
    const wrapper = mount(MarkdownView, { props: { source: SOURCE } })
    const preview = wrapper.find('[data-test="md-preview"]')
    expect(preview.exists()).toBe(true)
    expect(preview.find('h2').text()).toBe('Zadání')
    expect(preview.text()).not.toContain('skryté')
    expect(wrapper.find('[data-test="md-source"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="md-tab-preview"]').attributes('aria-selected')).toBe('true')
  })

  it('switches to source and back', async () => {
    const wrapper = mount(MarkdownView, { props: { source: SOURCE } })
    await wrapper.find('[data-test="md-tab-source"]').trigger('click')
    const src = wrapper.find('[data-test="md-source"]')
    expect(src.text()).toContain('## Zadání')
    expect(src.text()).toContain('<!-- skryté -->')
    expect(wrapper.find('[data-test="md-preview"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="md-tab-source"]').attributes('aria-selected')).toBe('true')
    await wrapper.find('[data-test="md-tab-preview"]').trigger('click')
    expect(wrapper.find('[data-test="md-preview"]').exists()).toBe(true)
  })

  it('shows a dash for empty source', () => {
    const wrapper = mount(MarkdownView, { props: { source: '  ' } })
    expect(wrapper.find('[data-test="md-empty"]').text()).toBe('—')
  })
})
