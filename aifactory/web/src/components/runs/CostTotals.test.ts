import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import CostTotals from './CostTotals.vue'
import { runTotals } from '@/test/runsFixtures'

const shown = { open: true, loading: false, error: null }

describe('CostTotals', () => {
  it('is folded by default and asks to open', async () => {
    const wrapper = mount(CostTotals, { props: { open: false, totals: null, loading: false, error: null } })
    expect(wrapper.find('[data-test="backlog-total"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="dsec-toggle"]').attributes('aria-expanded')).toBe('false')
    await wrapper.find('[data-test="dsec-toggle"]').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('shows loading until the totals arrive', () => {
    const wrapper = mount(CostTotals, { props: { ...shown, totals: null, loading: true } })
    expect(wrapper.find('[data-test="totals-loading"]').text()).toBe('Načítám…')
  })

  it('shows the backlog total and one row per task', () => {
    const wrapper = mount(CostTotals, { props: { ...shown, totals: runTotals() } })
    const backlog = wrapper.find('[data-test="backlog-total"]')
    expect(backlog.find('[data-col="cost"]').text()).toBe('$0.2600')
    expect(backlog.find('[data-col="tokens"]').text()).toBe('1.3k')
    expect(backlog.find('[data-col="runs"]').text()).toBe('2')
    const rows = wrapper.findAll('tbody tr')
    expect(rows.map((r) => r.attributes('data-task'))).toEqual(['M01-S01-T01', 'M01-S01-T02'])
    expect(rows[0]!.find('[data-col="cost"]').text()).toBe('$0.2500')
    expect(rows[1]!.text()).toContain('Loader')
  })

  it('shows each task as "ID Název", or only the id without a title', () => {
    const totals = runTotals()
    totals.tasks[0] = { ...totals.tasks[0]!, task_title: null }
    const wrapper = mount(CostTotals, { props: { ...shown, totals } })
    expect(wrapper.find('tr[data-task="M01-S01-T02"] [data-test="task-label"]').text()).toBe('M01-S01-T02 Loader')
    expect(wrapper.find('tr[data-task="M01-S01-T01"] [data-test="task-label"]').text()).toBe('M01-S01-T01')
  })

  it('shows an error', () => {
    const wrapper = mount(CostTotals, { props: { ...shown, totals: null, error: 'boom' } })
    expect(wrapper.find('[data-test="totals-error"]').text()).toBe('boom')
  })
})
