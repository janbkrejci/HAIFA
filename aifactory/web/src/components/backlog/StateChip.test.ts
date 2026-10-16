import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import StateChip from './StateChip.vue'

let wrapper: VueWrapper | null = null

afterEach(() => {
  wrapper?.unmount()
  wrapper = null
  document.body.innerHTML = ''
})

const BLOCKED_BY = [{ id: 'M01-S01-T02', reason: 'not_done', missing: ['M01-S01-T02'] }]

describe('StateChip', () => {
  it('shows what blocks the task in a tooltip', async () => {
    wrapper = mount(StateChip, { props: { state: 'blocked', blockedBy: BLOCKED_BY }, attachTo: document.body })
    expect(wrapper.find('[data-state="blocked"]').text()).toBe('Blokováno')
    await wrapper.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent?.trim()).toBe('Blokuje:\nM01-S01-T02 – task není hotový')
  })

  it('has no tooltip for other states or without blockers', () => {
    wrapper = mount(StateChip, { props: { state: 'ready', blockedBy: BLOCKED_BY } })
    expect(wrapper.find('[data-test="tip-anchor"]').exists()).toBe(false)
    expect(wrapper.find('[data-state="ready"]').text()).toBe('Připraveno')
    wrapper.unmount()
    wrapper = mount(StateChip, { props: { state: 'blocked', blockedBy: [] } })
    expect(wrapper.find('[data-test="tip-anchor"]').exists()).toBe(false)
    expect(wrapper.find('[data-state="blocked"]').text()).toBe('Blokováno')
  })

  it('names the todo state Bez workflow and explains it in a tooltip', async () => {
    wrapper = mount(StateChip, { props: { state: 'todo' }, attachTo: document.body })
    expect(wrapper.find('[data-state="todo"]').text()).toBe('Bez workflow')
    await wrapper.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')
    expect(tip?.textContent?.trim()).toBe(
      'Task nejde spustit, dokud nemá workflow (vlastní nebo zděděné z projektu či stepu).',
    )
  })

  it('carries the shared state colour classes', () => {
    wrapper = mount(StateChip, { props: { state: 'in review', count: 2 } })
    const chip = wrapper.find('[data-state="in review"]')
    expect(chip.classes()).toEqual(expect.arrayContaining(['state-chip', 'state-in-review']))
    expect(chip.text()).toBe('Čeká na review 2')
  })

  it('tells a PR waiting for auto-merge apart from one waiting for review', () => {
    wrapper = mount(StateChip, { props: { state: 'awaiting merge', count: 1 } })
    const chip = wrapper.find('[data-state="awaiting merge"]')
    expect(chip.classes()).toEqual(expect.arrayContaining(['state-chip', 'state-awaiting-merge']))
    expect(chip.text()).toBe('Čeká na automerge PR 1')
  })

  it('names a person\'s task and a task that waits for one', () => {
    wrapper = mount(StateChip, { props: { state: 'human' } })
    expect(wrapper.find('[data-state="human"]').text()).toBe('Pro člověka')
    wrapper.unmount()
    wrapper = mount(StateChip, {
      props: { state: 'blocked', waitsForHuman: ['M01-S01-T01'], blockedBy: [{ id: 'M01-S01-T01', reason: 'not_done', missing: ['M01-S01-T01'] }] },
    })
    const chip = wrapper.find('[data-state="blocked"]')
    expect(chip.text()).toBe('Čeká na člověka')
    expect(chip.classes()).toContain('state-human')
  })
})
