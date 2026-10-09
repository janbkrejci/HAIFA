import { describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { mergeNames, resetNamesForTests } from '@/lib/names'
import ReviewList from './ReviewList.vue'
import { fmtTime } from '@/lib/format'
import { donePr, reviewList, reviewPr, taskPr } from '@/test/reviewFixtures'

describe('ReviewList', () => {
  it('splits PRs awaiting review from the others', () => {
    const wrapper = mount(ReviewList, { props: { list: reviewList() } })
    const awaiting = wrapper.find('[data-test="awaiting"]')
    const other = wrapper.find('[data-test="other"]')
    expect(awaiting.findAll('tr[data-pr]').map((r) => r.attributes('data-pr'))).toEqual(['M01-S01-T01'])
    expect(other.findAll('tr[data-pr]').map((r) => r.attributes('data-pr'))).toEqual(['M02-S01-T01'])
    expect(awaiting.text()).toContain('Čeká na review')
    expect(other.text()).toContain('Ostatní otevřené PR')
  })

  it('names the project column by the top level and shows the title of codes', async () => {
    mergeNames({ M01: { title: 'Core', level: 'project' } })
    const wrapper = mount(ReviewList, {
      props: { list: reviewList({ levels: ['project', 'step', 'task'] }) },
      attachTo: document.body,
    })
    const headers = wrapper.find('[data-test="awaiting"]').findAll('th').map((h) => h.text())
    expect(headers[1]).toBe('Projekt')
    const cell = wrapper.find('tr[data-pr="M01-S01-T01"] [data-col="project"]')
    await cell.find('[data-test="tip-anchor"]').trigger('mouseenter')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent?.trim()).toBe('Projekt: Core')
    wrapper.unmount()
    resetNamesForTests()
    document.body.innerHTML = ''
  })

  it('shows module, mergeability, costs and links', () => {
    const wrapper = mount(ReviewList, { props: { list: reviewList() } })
    const headers = wrapper.find('[data-test="awaiting"]').findAll('th').map((h) => h.text())
    expect(headers).toEqual(['Task', 'Modul', 'Mergeabilita', 'Běh', 'Náklady', 'Tokeny', 'PR'])
    const row = wrapper.find('tr[data-pr="M01-S01-T01"]')
    expect(row.find('[data-col="project"]').text()).toBe('M01')
    expect(row.find('[data-test="mergeability"]').text()).toBe('lze mergovat')
    expect(row.find('[data-col="cost"]').text()).toBe('$0.2500')
    expect(row.find('[data-col="tokens"]').text()).toBe('1.2k')
    expect(row.find('a.task-link').attributes('href')).toBe('#/r/haifa/review/M01-S01-T01')
    const pr = row.find('a[data-col="pr"]')
    expect(pr.attributes('href')).toBe('https://example.test/pr/7')
    expect(pr.attributes('target')).toBe('_blank')
    expect(pr.attributes('rel')).toBe('noopener')
    const other = wrapper.find('tr[data-pr="M02-S01-T01"]')
    expect(other.find('[data-test="mergeability"]').text()).toBe('konflikt')
    expect(other.find('[data-col="cost"]').text()).toBe('$1.50')
    expect(other.find('[data-col="run"] a').attributes('href')).toBe('#/r/haifa/runs/r-run')
    expect(other.find('a[data-col="pr"]').exists()).toBe(false)
    expect(other.find('[data-col="pr"]').text()).toBe('local:factory/M02-S01-T01-1')
  })

  it('has no owner filter, "Jen moje moduly" or owner column', () => {
    const wrapper = mount(ReviewList, { props: { list: reviewList() } })
    for (const sel of ['owner-filter', 'mine-only', 'me-hint']) {
      expect(wrapper.find(`[data-test="${sel}"]`).exists()).toBe(false)
    }
    expect(wrapper.find('[data-col="owner"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('Vlastník')
    expect(wrapper.text()).not.toContain('Jen moje moduly')
  })

  it('shows an empty state with the way on', () => {
    const wrapper = mount(ReviewList, { props: { list: reviewList({ prs: [] }) } })
    expect(wrapper.find('[data-test="no-prs"]').text()).toContain('Žádné PR ke schválení')
    expect(wrapper.find('[data-test="no-prs-backlog"]').attributes('href')).toBe('#/r/haifa/backlog')
    expect(wrapper.find('[data-test="no-prs-runs"]').attributes('href')).toBe('#/r/haifa/runs')
  })

  it('shows the task as "ID Název", or only the id without a title', () => {
    const list = reviewList({
      prs: [
        reviewPr({ task_id: 'M01-S01-T02', task_title: 'Loader' }),
        reviewPr({ task_id: 'M01-S01-T03', task_title: null }),
      ],
    })
    const wrapper = mount(ReviewList, { props: { list } })
    expect(wrapper.find('tr[data-pr="M01-S01-T02"] [data-test="task-label"]').text()).toBe('M01-S01-T02 Loader')
    expect(wrapper.find('tr[data-pr="M01-S01-T03"] [data-test="task-label"]').text()).toBe('M01-S01-T03')
  })

  it('has no "Hotové" section unless asked', () => {
    const wrapper = mount(ReviewList, { props: { list: reviewList({ done: [donePr()] }) } })
    expect(wrapper.find('[data-test="done"]').exists()).toBe(false)
    expect(wrapper.find('tr[data-done-pr]').exists()).toBe(false)
  })

  it('shows merged and closed PRs under the open ones, newest first', () => {
    const older = donePr({
      task_id: 'M04-S01-T01',
      task_title: 'Old',
      project_id: 'M04',
      provider_state: 'closed',
      done_at: '2026-01-01T08:00:00+00:00',
      pr: taskPr({ task_id: 'M04-S01-T01', branch: 'factory/M04-S01-T01-1', url: 'local:factory/M04-S01-T01-1', state: 'closed' }),
    })
    const newer = donePr()
    const wrapper = mount(ReviewList, {
      props: { list: reviewList({ done: [older, newer] }), showDone: true },
    })
    const section = wrapper.find('[data-test="done"]')
    expect(section.find('h2').text()).toBe('Hotové (2)')
    expect(wrapper.html().indexOf('data-test="other"')).toBeLessThan(wrapper.html().indexOf('data-test="done"'))
    expect(section.findAll('th').map((h) => h.text())).toEqual(['Task', 'Modul', 'Stav', 'Datum', 'Náklady', 'PR'])
    const rows = section.findAll('tr[data-done-pr]')
    expect(rows.map((r) => r.attributes('data-done-pr'))).toEqual(['M03-S01-T01', 'M04-S01-T01'])
    expect(wrapper.findAll('tr[data-pr]')).toHaveLength(2)
    const [first, second] = rows
    expect(first.find('[data-col="state"]').text()).toBe('sloučeno')
    expect(first.find('[data-col="state"]').attributes('data-state')).toBe('merged')
    expect(first.find('[data-col="done-at"]').text()).toBe(fmtTime(newer.done_at))
    expect(first.find('a.task-link').attributes('href')).toBe('#/r/haifa/review/M03-S01-T01')
    expect(first.find('[data-test="task-label"]').text()).toBe('M03-S01-T01 Export')
    const link = first.find('a[data-col="pr"]')
    expect(link.attributes('href')).toBe('https://example.test/pr/9')
    expect(link.attributes('target')).toBe('_blank')
    expect(second.find('[data-col="state"]').text()).toBe('zavřeno')
    expect(second.find('[data-col="done-at"]').text()).toBe(fmtTime(older.done_at))
    expect(second.find('[data-col="pr"]').text()).toBe('local:factory/M04-S01-T01-1')
  })

  it('shows "Hotové" also without open PRs, and "Nic" without done PRs', () => {
    const both = mount(ReviewList, {
      props: { list: reviewList({ prs: [], done: [donePr()] }), showDone: true },
    })
    expect(both.find('[data-test="no-prs"]').text()).toContain('Žádné PR ke schválení')
    expect(both.findAll('tr[data-done-pr]')).toHaveLength(1)
    const none = mount(ReviewList, { props: { list: reviewList({ done: [] }), showDone: true } })
    expect(none.find('[data-test="done"]').text()).toContain('Nic')
    const missing = mount(ReviewList, { props: { list: reviewList(), showDone: true } })
    expect(missing.find('[data-test="done"]').text()).toContain('Nic')
  })
})
