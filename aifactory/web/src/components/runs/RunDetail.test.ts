import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RunDetail from './RunDetail.vue'
import { detail, events, okResponse, prompts } from '@/test/runsFixtures'
import { answerDialog, openDialog } from '@/test/modal'

// Unmount every wrapper so no late render runs after the environment is torn down.
enableAutoUnmount(afterEach)

afterEach(() => {
  vi.restoreAllMocks()
})

describe('RunDetail', () => {
  it('draws the phases as a waterfall instead of a table', () => {
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: events() } })
    expect(wrapper.find('table.phases').exists()).toBe(false)
    expect(wrapper.find('[data-test="waterfall"]').exists()).toBe(true)
    const blocks = wrapper.findAll('button.block[data-phase]')
    expect(blocks.map((b) => b.attributes('data-phase')).sort()).toEqual(['p1', 'p2'])
    expect(wrapper.find('button.block[data-phase="p1"]').text()).toContain('plan')
    expect(wrapper.find('button.block[data-phase="p2"]').classes()).toContain('failed')
    expect(wrapper.find('[data-test="pr-link"]').attributes('href')).toBe('https://example.test/pr/7')
  })

  it('links the task to the backlog and its PR to Review, the PR state in Czech', () => {
    window.location.hash = '#/r/haifa/runs/r-1'
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: events() } })
    const task = wrapper.get('[data-test="task-link"]')
    expect(task.attributes('href')).toBe(`#/r/haifa/backlog/${task.text()}`)
    const pr = wrapper.get('[data-test="pr-link"]')
    expect(pr.attributes('target')).toBe('_blank')
    expect(pr.attributes('rel')).toBe('noopener')
    expect(pr.text()).not.toMatch(/\((open|merged|closed)\)/)
    expect(wrapper.get('[data-test="pr-review"]').attributes('href')).toBe(`#/r/haifa/review/${task.text()}`)
  })

  it('says who started the run', () => {
    const manual = mount(RunDetail, { props: { detail: detail(), events: events() } })
    expect(manual.get('[data-test="started-by"]').text()).toBe('Spuštěno ručně (dashboard nebo factory task run)')
    const auto = mount(RunDetail, { props: { detail: detail({ started_by: 'auto-resolve' }), events: events() } })
    expect(auto.get('[data-test="started-by"]').text()).toBe('Spuštěno automaticky: auto-merge řeší konflikt PR')
  })

  it('shows the selected phase detail', () => {
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: events(), phaseId: 'p2' } })
    expect(wrapper.find('.phase-detail').attributes('data-phase')).toBe('p2')
    expect(wrapper.find('.block.selected').attributes('data-phase')).toBe('p2')
    expect(wrapper.find('[data-test="phase-hint"]').exists()).toBe(false)
  })

  it('shows no phase panel until a phase is picked', () => {
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: events() } })
    expect(wrapper.find('.phase-detail').exists()).toBe(false)
    expect(wrapper.find('.block.selected').exists()).toBe(false)
    expect(wrapper.find('[data-test="phase-hint"]').text()).toContain('Vyber fázi')
  })

  it('passes the run request and closes the panel back to the run', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse(prompts())))
    window.location.hash = '#/r/haifa/runs/r-ok/p1'
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: events(), phaseId: 'p1' } })
    await flushPromises()
    expect(wrapper.find('[data-section="request"]').exists()).toBe(true)
    await wrapper.find('[data-test="phase-close"]').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/runs/r-ok')
    window.location.hash = ''
    vi.unstubAllGlobals()
  })

  it('offers Stop only for a running run', () => {
    const done = mount(RunDetail, { props: { detail: detail(), events: [] } })
    expect(done.find('[data-test="stop-run"]').exists()).toBe(false)
    const running = mount(RunDetail, { props: { detail: detail({ state: 'running' }), events: [] } })
    expect(running.find('[data-test="stop-run"]').exists()).toBe(true)
  })

  it('offers Pauza for a running run and Pokračovat for a paused one', async () => {
    const done = mount(RunDetail, { props: { detail: detail(), events: [] } })
    expect(done.find('[data-test="pause-run"]').exists()).toBe(false)
    expect(done.find('[data-test="resume-run"]').exists()).toBe(false)

    const running = mount(RunDetail, { props: { detail: detail({ state: 'running' }), events: [] } })
    expect(running.find('[data-test="resume-run"]').exists()).toBe(false)
    await running.get('[data-test="pause-run"]').trigger('click')
    expect(running.emitted('pause')).toHaveLength(1)

    const paused = mount(RunDetail, {
      props: { detail: detail({ state: 'running', pause: 'paused' }), events: [] },
    })
    expect(paused.find('[data-test="pause-run"]').exists()).toBe(false)
    expect(paused.find('.chip').attributes('data-status')).toBe('paused')
    expect(paused.find('.chip').text()).toBe('pozastaveno')
    // A paused run can still be stopped.
    expect(paused.find('[data-test="stop-run"]').exists()).toBe(true)
    await paused.get('[data-test="resume-run"]').trigger('click')
    expect(paused.emitted('resume')).toHaveLength(1)

    const pausing = mount(RunDetail, {
      props: { detail: detail({ state: 'running', pause: 'pausing' }), events: [] },
    })
    expect(pausing.find('.chip').attributes('data-status')).toBe('pausing')
    expect(pausing.find('[data-test="resume-run"]').exists()).toBe(true)

    const busy = mount(RunDetail, {
      props: { detail: detail({ state: 'running' }), events: [], pauseBusy: true },
    })
    expect(busy.get('[data-test="pause-run"]').attributes('disabled')).toBeDefined()
  })

  it('emits stop after confirmation in the modal', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    const wrapper = mount(RunDetail, {
      props: { detail: detail({ state: 'running' }), events: [] },
      attachTo: document.body,
    })
    await wrapper.find('[data-test="stop-run"]').trigger('click')
    await flushPromises()
    expect(openDialog()?.textContent).toContain('Zastavit běh')
    await answerDialog(false)
    expect(wrapper.emitted('stop')).toBeUndefined()
    await wrapper.find('[data-test="stop-run"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.emitted('stop')).toHaveLength(1)
    expect(confirmSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('shows pr_error and offers Publish for a succeeded run without a PR', async () => {
    const failed = mount(RunDetail, {
      props: { detail: detail({ pr: null, pr_error: 'push_failed: RPC failed' }), events: [] },
    })
    expect(failed.get('[data-test="pr-error"]').text()).toContain('push_failed: RPC failed')
    await failed.get('[data-test="publish-run"]').trigger('click')
    expect(failed.emitted('publish')).toHaveLength(1)
    const busy = mount(RunDetail, {
      props: { detail: detail({ pr: null }), events: [], publishing: true },
    })
    expect(busy.get('[data-test="publish-run"]').attributes('disabled')).toBeDefined()
  })

  it('offers no Publish for a run with a PR or one that did not succeed', () => {
    const withPr = mount(RunDetail, { props: { detail: detail(), events: [] } })
    expect(withPr.find('[data-test="publish-run"]').exists()).toBe(false)
    expect(withPr.find('[data-test="pr-error"]').exists()).toBe(false)
    const failed = mount(RunDetail, { props: { detail: detail({ state: 'failed', pr: null }), events: [] } })
    expect(failed.find('[data-test="publish-run"]').exists()).toBe(false)
  })

  it('shows stat tooltips without a native title', async () => {
    const wrapper = mount(RunDetail, { props: { detail: detail(), events: [] }, attachTo: document.body })
    const stat = wrapper.find('[data-stat="cost"]')
    expect(stat.attributes('title')).toBeUndefined()
    await stat.trigger('focusin')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toContain('Náklady')
    await stat.trigger('focusout')
    expect(document.body.querySelector('[data-test="tooltip"]')).toBeNull()
    expect(wrapper.find('[title]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('says the PR was merged by auto-merge, or why it was not', () => {
    const merged = mount(RunDetail, {
      props: {
        detail: detail({ pr: { url: 'https://example.test/pr/7', pr_id: '7', state: 'merged', merged_by: 'auto-merge' } }),
        events: events(),
      },
    })
    expect(merged.find('[data-test="pr-merged-by"]').text()).toBe('sloučil auto-merge')
    const open = mount(RunDetail, {
      props: {
        detail: detail({
          pr: { url: 'https://example.test/pr/7', pr_id: '7', state: 'open', auto_merge_error: 'conflict: no' },
        }),
        events: events(),
      },
    })
    expect(open.find('[data-test="pr-merged-by"]').exists()).toBe(false)
    expect(open.find('[data-test="pr-auto-merge-error"]').text()).toContain('conflict: no')
  })

  it('shows the task in the header as "ID Název"', () => {
    const wrapper = mount(RunDetail, {
      props: { detail: detail({ task_id: 'M01-S01-T02', task_title: 'Loader' }), events: events() },
    })
    expect(wrapper.find('[data-test="task-label"]').text()).toBe('M01-S01-T02 Loader')
    const bare = mount(RunDetail, { props: { detail: detail({ task_title: null }), events: events() } })
    expect(bare.find('[data-test="task-label"]').text()).toBe('M01-S01-T01')
  })

  it('grows running durations every second without fetching', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T10:00:10Z'))
    const fetchSpy = vi.fn()
    vi.stubGlobal('fetch', fetchSpy)
    try {
      const d = detail({ state: 'running', ended_at: null, duration_s: null })
      d.phases = [{ ...d.phases[1]!, status: 'running', ended_at: null, duration_s: null }]
      const wrapper = mount(RunDetail, { props: { detail: d, events: [] } })
      const dur = () => wrapper.find('button.block[data-phase="p1"] .b-dur').text()
      expect(dur()).toBe('10.0s')
      expect(wrapper.find('.stats [data-stat="runtime"]').text()).toBe('10.0s')
      vi.advanceTimersByTime(3000)
      await nextTick()
      expect(dur()).toBe('13.0s')
      expect(wrapper.find('.stats [data-stat="runtime"]').text()).toBe('13.0s')
      expect(fetchSpy).not.toHaveBeenCalled()
      wrapper.unmount()
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
      vi.unstubAllGlobals()
    }
  })

  it('does not tick for a finished run', () => {
    vi.useFakeTimers()
    try {
      mount(RunDetail, { props: { detail: detail(), events: [] } })
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      vi.useRealTimers()
    }
  })
})
