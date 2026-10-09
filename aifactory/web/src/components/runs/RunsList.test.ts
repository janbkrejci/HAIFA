import { afterEach, describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import RunsList from './RunsList.vue'
import { runsResponse } from '@/test/runsFixtures'

afterEach(() => {
  document.body.innerHTML = ''
})

describe('RunsList', () => {
  it('renders every column of a run', () => {
    const data = runsResponse()
    const wrapper = mount(RunsList, { props: { runs: data.runs } })
    const headers = wrapper.findAll('th').map((h) => h.text())
    expect(headers).toEqual(['Task', 'Workflow', 'Stav', 'Začátek', 'Spustil', 'Doba', 'Tokeny', 'Náklady', 'PR', 'Fáze', ''])
    const row = wrapper.find('tr[data-run="r-ok"]')
    expect(row.text()).toContain('M01-S01-T01')
    expect(row.text()).toContain('Schema')
    expect(row.text()).toContain('plan-commit')
    expect(row.text()).toContain('úspěch')
    expect(row.find('[data-col="duration"]').text()).toBe('5m 00s')
    expect(row.find('[data-col="tokens"]').text()).toBe('1.2k')
    expect(row.find('[data-col="cost"]').text()).toBe('$0.2500')
    const pr = row.find('a[data-col="pr"]')
    expect(pr.attributes('href')).toBe('https://example.test/pr/7')
    expect(pr.attributes('target')).toBe('_blank')
    expect(pr.attributes('rel')).toBe('noopener')
    expect(row.find('a.task-link').attributes('href')).toBe('#/r/haifa/runs/r-ok')
    expect(row.find('[data-col="started-by"]').text()).toBe('ručně')
    const running = wrapper.find('tr[data-run="r-run"]')
    expect(running.find('[data-col="started-by"]').text()).toBe('auto-continue')
    expect(running.text()).toContain('běží')
    expect(running.find('a[data-col="pr"]').exists()).toBe(false)
  })

  it('has no state or task filter', () => {
    const data = runsResponse()
    const wrapper = mount(RunsList, { props: { runs: data.runs } })
    expect(wrapper.find('[data-test="state-filter"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="task-filter"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="view-active"]').exists()).toBe(true)
  })

  it('shows an empty state', () => {
    const wrapper = mount(RunsList, { props: { runs: [] } })
    expect(wrapper.find('[data-test="no-runs"]').text()).toBe('Žádné běhy')
    expect(wrapper.find('table').exists()).toBe(false)
  })

  it('shows the task as "ID Název", or only the id without a title', () => {
    const data = runsResponse()
    const runs = [...data.runs, { ...data.runs[0]!, run_id: 'r-untitled', task_id: 'M01-S01-T01', task_title: null }]
    const wrapper = mount(RunsList, { props: { runs } })
    expect(wrapper.find('tr[data-run="r-run"] [data-test="task-label"]').text()).toBe('M01-S01-T02 Loader')
    expect(wrapper.find('tr[data-run="r-untitled"] [data-test="task-label"]').text()).toBe('M01-S01-T01')
  })

  it('switches between the active and the archived runs', async () => {
    const data = runsResponse()
    const wrapper = mount(RunsList, { props: { runs: data.runs } })
    expect(wrapper.find('[data-test="hide-done"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="view-active"]').attributes('aria-pressed')).toBe('true')
    await wrapper.find('[data-test="view-archived"]').trigger('click')
    expect(wrapper.emitted('update:archived')?.[0]).toEqual([true])
    await wrapper.setProps({ archived: true })
    expect(wrapper.find('[data-test="view-archived"]').attributes('aria-pressed')).toBe('true')
    await wrapper.find('[data-test="view-active"]').trigger('click')
    expect(wrapper.emitted('update:archived')?.[1]).toEqual([false])
  })

  it('offers "Archivovat dokončené" and an archive icon on finished active runs', async () => {
    const data = runsResponse()
    const wrapper = mount(RunsList, { props: { runs: data.runs } })
    expect(wrapper.find('[data-test="delete-archived"]').exists()).toBe(false)
    await wrapper.find('[data-test="archive-finished"]').trigger('click')
    expect(wrapper.emitted('archive-finished')).toHaveLength(1)
    // a running run cannot be archived
    expect(wrapper.find('tr[data-run="r-run"] [data-test="archive"]').exists()).toBe(false)
    const row = wrapper.find('tr[data-run="r-ok"]')
    expect(row.find('[data-test="unarchive"]').exists()).toBe(false)
    expect(row.find('[data-test="delete"]').exists()).toBe(false)
    await row.find('[data-test="archive"]').trigger('click')
    expect(wrapper.emitted('archive')?.[0]).toEqual(['r-ok'])
  })

  it('offers "Vymazat všechny", unarchive and then delete on archived runs', async () => {
    const data = runsResponse()
    const runs = [{ ...data.runs[1]!, archived: true }]
    const wrapper = mount(RunsList, { props: { runs, archived: true } })
    expect(wrapper.find('[data-test="archive-finished"]').exists()).toBe(false)
    await wrapper.find('[data-test="delete-archived"]').trigger('click')
    expect(wrapper.emitted('delete-archived')).toHaveLength(1)
    const row = wrapper.find('tr[data-run="r-ok"]')
    expect(row.find('[data-test="archive"]').exists()).toBe(false)
    const actions = row.findAll('td.actions button').map((b) => b.attributes('data-test'))
    expect(actions).toEqual(['unarchive', 'delete'])
    await row.find('[data-test="unarchive"]').trigger('click')
    expect(wrapper.emitted('unarchive')?.[0]).toEqual(['r-ok'])
    await row.find('[data-test="delete"]').trigger('click')
    expect(wrapper.emitted('delete')?.[0]).toEqual(['r-ok'])
    // a click on an icon does not open the run
    expect(window.location.hash).not.toBe('#/r/haifa/runs/r-ok')
  })

  it('opens the run on a click anywhere on the row, archived ones too', async () => {
    window.location.hash = '#/r/haifa/runs'
    const data = runsResponse()
    const runs = [{ ...data.runs[1]!, archived: true }]
    const wrapper = mount(RunsList, { props: { runs, archived: true } })
    await wrapper.find('tr[data-run="r-ok"] [data-col="tokens"]').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/runs/r-ok')
    window.location.hash = '#/r/haifa/runs'
  })

  it('shows an empty archived list and disables "Vymazat všechny"', () => {
    const wrapper = mount(RunsList, { props: { runs: [], archived: true } })
    expect(wrapper.find('[data-test="no-runs"]').text()).toBe('Žádné archivované běhy')
    expect(wrapper.find('[data-test="delete-archived"]').attributes('disabled')).toBeDefined()
  })
})
