import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import DiffView from './DiffView.vue'
import { reviewDetail } from '@/test/reviewFixtures'

describe('DiffView', () => {
  it('shows files, counts and coloured lines', async () => {
    const diff = reviewDetail().diff
    const wrapper = mount(DiffView, { props: { diff } })
    expect(wrapper.findAll('[data-test="diff-file"]')).toHaveLength(0)
    const sections = wrapper.findAll('[data-test="diff-file-section"]')
    expect(sections.map((s) => s.attributes('data-path'))).toEqual(['specs/x.md', 'img/logo.png'])
    for (const head of wrapper.findAll('button.dsec-head')) await head.trigger('click')
    expect(wrapper.find('[data-test="diff-stat"]').text()).toContain('2 souborů')
    expect(wrapper.find('[data-test="diff-stat"]').text()).toContain('+3')
    const files = wrapper.findAll('[data-test="diff-file"]')
    expect(files.map((f) => f.attributes('data-path'))).toEqual(['specs/x.md', 'img/logo.png'])
    expect(files[0].text()).toContain('přidán')
    expect(files[0].text()).toContain('+2')
    const added = files[0].findAll('[data-kind="add"]').map((l) => l.text())
    expect(added).toEqual(['+# spec', '+body'])
    expect(files[0].find('[data-kind="hunk"]').text()).toBe('@@ -0,0 +1,2 @@')
    expect(files[1].find('[data-test="binary"]').text()).toBe('binární soubor')
  })

  it('marks a truncated patch and an empty diff', async () => {
    const base = reviewDetail().diff
    const file = { ...base.files[0], truncated: true }
    const wrapper = mount(DiffView, { props: { diff: { ...base, files: [file] } } })
    await wrapper.find('button.dsec-head').trigger('click')
    expect(wrapper.find('[data-test="truncated"]').text()).toBe('diff zkrácen')
    const empty = mount(DiffView, {
      props: { diff: { ...base, stat: { files: 0, additions: 0, deletions: 0 }, files: [] } },
    })
    expect(empty.find('[data-test="no-diff"]').exists()).toBe(true)
  })
})
