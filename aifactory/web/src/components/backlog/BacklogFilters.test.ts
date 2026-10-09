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

  it('filters the kanban by project and step with labels from levels', async () => {
    const projects = [
      { id: 'P1', title: 'One' },
      { id: 'P2', title: null },
    ]
    const steps = [
      { id: 'P1-S01', title: 'A', path: 'p1/s1', project: 'P1' },
      { id: 'P2-S01', title: 'B', path: 'p2/s1', project: 'P2' },
    ]
    const props = { filters: {}, mode: 'kanban' as const, levels: ['project', 'step', 'task'], projects, steps }
    const wrapper = mount(BacklogFilters, { props })
    expect(wrapper.find('[data-test="project-filter"]').element.parentElement?.textContent).toContain('Projekt')
    expect(wrapper.find('[data-test="step-filter"]').element.parentElement?.textContent).toContain('Step')
    expect(await selectLabels(wrapper, '[data-test="project-filter"]')).toEqual(['vše', 'P1 – One', 'P2'])
    expect(await selectLabels(wrapper, '[data-test="step-filter"]')).toEqual(['vše', 'P1-S01 – A', 'P2-S01 – B'])
    await chooseOption(wrapper, '[data-test="project-filter"]', 'P1')
    expect(wrapper.emitted('update:filters')?.[0]).toEqual([{ project: 'P1', step: undefined }])
    await wrapper.setProps({ filters: { project: 'P1' } })
    expect(await selectLabels(wrapper, '[data-test="step-filter"]')).toEqual(['vše', 'P1-S01 – A'])
    await chooseOption(wrapper, '[data-test="step-filter"]', 'P1-S01')
    expect(wrapper.emitted('update:filters')?.[1]).toEqual([{ project: 'P1', step: 'P1-S01' }])
    // another project drops a step outside it
    await wrapper.setProps({ filters: { project: 'P1', step: 'P1-S01' } })
    await chooseOption(wrapper, '[data-test="project-filter"]', 'P2')
    expect(wrapper.emitted('update:filters')?.[2]).toEqual([{ project: 'P2', step: undefined }])
  })

  it('has no step filter with fewer than three levels and no scope filters in the tree', async () => {
    const wrapper = mount(BacklogFilters, {
      props: { filters: {}, mode: 'kanban', levels: ['area', 'task'], projects: [{ id: 'A', title: null }] },
    })
    expect(wrapper.find('[data-test="project-filter"]').element.parentElement?.textContent).toContain('area')
    expect(wrapper.find('[data-test="step-filter"]').exists()).toBe(false)
    await wrapper.setProps({ mode: 'tree' })
    expect(wrapper.find('[data-test="project-filter"]').exists()).toBe(false)
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
