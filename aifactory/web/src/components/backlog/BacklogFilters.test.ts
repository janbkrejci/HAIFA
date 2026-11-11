import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import BacklogFilters from './BacklogFilters.vue'
import { chooseOption, selectLabels } from '@/test/select'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('BacklogFilters', () => {
  it('has no status or owner filter, in the tree nor in the kanban', () => {
    for (const mode of ['tree', 'kanban'] as const) {
      const wrapper = mount(BacklogFilters, { props: { filters: {}, mode } })
      expect(wrapper.find('[data-test="state-filter"]').exists()).toBe(false)
      expect(wrapper.find('[data-test="owner-filter"]').exists()).toBe(false)
      expect(wrapper.text()).not.toContain('Stav')
      expect(wrapper.text()).not.toContain('Vlastník')
    }
  })

  it('switches the mode', async () => {
    const wrapper = mount(BacklogFilters, { props: { filters: {}, mode: 'tree' } })
    expect(wrapper.find('[data-test="mode-tree"]').classes()).toContain('active')
    await wrapper.find('[data-test="mode-kanban"]').trigger('click')
    expect(wrapper.emitted('update:mode')?.[0]).toEqual(['kanban'])
  })

  it.each(['tree', 'kanban'] as const)('filters %s by project with labels from levels', async (mode) => {
    const projects = [{ id: 'P1', title: 'One' }, { id: 'P2', title: null }]
    const wrapper = mount(BacklogFilters, {
      props: { filters: {}, mode, levels: ['project', 'step', 'task'], projects },
    })
    expect(wrapper.find('[data-test="project-filter"]').element.parentElement?.textContent).toContain('Projekt')
    expect(wrapper.find('[data-test="step-filter"]').exists()).toBe(false)
    expect(await selectLabels(wrapper, '[data-test="project-filter"]')).toEqual(['vše', 'P1 – One', 'P2'])
    await chooseOption(wrapper, '[data-test="project-filter"]', 'P1')
    expect(wrapper.emitted('update:filters')?.[0]).toEqual([{ project: 'P1' }])
    await wrapper.setProps({ filters: { project: 'P1' } })
    await chooseOption(wrapper, '[data-test="project-filter"]', '')
    expect(wrapper.emitted('update:filters')?.[1]).toEqual([{ project: undefined }])
  })

  it('uses the top level label with fewer than three levels in either view', async () => {
    const wrapper = mount(BacklogFilters, {
      props: { filters: {}, mode: 'kanban', levels: ['area', 'task'], projects: [{ id: 'A', title: null }] },
    })
    expect(wrapper.find('[data-test="project-filter"]').element.parentElement?.textContent).toContain('area')
    expect(wrapper.find('[data-test="step-filter"]').exists()).toBe(false)
    await wrapper.setProps({ mode: 'tree' })
    expect(wrapper.find('[data-test="project-filter"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="step-filter"]').exists()).toBe(false)
  })

  it('switches Skrýt hotové', async () => {
    const wrapper = mount(BacklogFilters, { props: { filters: {}, mode: 'tree' } })
    const box = wrapper.find<HTMLInputElement>('[data-test="hide-done"]')
    expect(box.element.checked).toBe(false)
    expect(wrapper.text()).toContain('Skrýt hotové')
    await box.setValue(true)
    expect(wrapper.emitted('update:hideDone')?.[0]).toEqual([true])
    await wrapper.setProps({ hideDone: true })
    expect(box.element.checked).toBe(true)
    await box.setValue(false)
    expect(wrapper.emitted('update:hideDone')?.[1]).toEqual([false])
  })
})
