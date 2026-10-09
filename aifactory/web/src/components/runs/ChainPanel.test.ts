import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ChainPanel from './ChainPanel.vue'
import type { Chain } from '@/lib/chains'

function chain(over: Partial<Chain> = {}): Chain {
  return {
    chain_id: 'c1',
    task_id: 'M01-S01-T01',
    state: 'running',
    stop: null,
    max_parallel: 3,
    started_at: '2026-01-01T10:00:00+00:00',
    updated_at: '2026-01-01T10:01:00+00:00',
    ended_at: null,
    runs: [
      { run_id: 'r1', task_id: 'M01-S01-T01', state: 'running' },
      { run_id: 'r2', task_id: 'M01-S01-T03', state: 'succeeded' },
    ],
    running: 1,
    free_slots: 2,
    skipped: [
      {
        task_id: 'M01-S01-T02',
        reason: 'writes_overlap',
        detail: 'běh r1 (M01-S01-T01): src/app/',
        waits_on: ['M01-S01-T01'],
      },
      { task_id: 'M01-S01-T04', reason: 'exclusive', detail: 'běží jen samostatně', waits_on: [] },
    ],
    exclusive: ['M01-S01-T05'],
    ...over,
  }
}

describe('ChainPanel', () => {
  it('shows nothing without chains', () => {
    const wrapper = mount(ChainPanel, { props: { chains: [] } })
    expect(wrapper.find('[data-test="chain-panel"]').exists()).toBe(false)
  })

  it('shows runs, slots, tasks run alone and skipped tasks with their reason', () => {
    const wrapper = mount(ChainPanel, { props: { chains: [chain()] } })
    expect(wrapper.get('[data-test="chain-state"]').text()).toContain('běží')
    expect(wrapper.get('[data-test="chain-slots"]').text()).toBe('Sloty: 1/3 (volné 2)')
    const runs = wrapper.findAll('[data-test="chain-run"]')
    expect(runs.map((r) => r.text())).toEqual([
      expect.stringContaining('M01-S01-T01'),
      expect.stringContaining('M01-S01-T03'),
    ])
    expect(runs[0].get('a').attributes('href')).toContain('r1')
    expect(wrapper.get('[data-test="chain-exclusive"]').text()).toContain('M01-S01-T05')
    const skips = wrapper.findAll('[data-test="chain-skip"]')
    expect(skips[0].text()).toContain('překryv writes')
    expect(skips[0].text()).toContain('src/app/')
    expect(skips[1].text()).toContain('jen samostatně')
  })

  it('links the tasks of a chain to the backlog and names an excluded skip', () => {
    window.location.hash = '#/r/haifa/runs'
    const skipped = [{ task_id: 'M01-S01-T09', reason: 'excluded', detail: 'vyloučeno z auto continue v kanbanu', waits_on: [] }]
    const wrapper = mount(ChainPanel, { props: { chains: [chain({ skipped })] } })
    expect(wrapper.get('[data-test="chain-task"]').attributes('href')).toMatch(/^#\/r\/haifa\/backlog\//)
    const skip = wrapper.get('[data-test="chain-skip"]')
    expect(skip.get('[data-test="chain-skip-task"]').attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T09')
    expect(skip.get('[data-reason="excluded"]').text()).toBe('odloženo v kanbanu')
    expect(wrapper.get('[data-test="chain-exclusive"] a').attributes('href')).toBe('#/r/haifa/backlog/M01-S01-T05')
  })

  it('shows the stop of an ended chain', () => {
    const wrapper = mount(ChainPanel, {
      props: { chains: [chain({ state: 'finished', stop: 'failed', free_slots: 0, exclusive: [] })] },
    })
    expect(wrapper.get('[data-test="chain-state"]').text()).toContain('skončil: běh selhal')
    expect(wrapper.find('[data-test="chain-exclusive"]').exists()).toBe(false)
  })

  it('shows the result of every run: workflow, PR, what auto-merge did, error', () => {
    const pr = { url: 'https://example.test/pr/7', pr_id: '7', state: 'merged', merged_by: 'auto-merge' }
    const runs = [
      { run_id: 'r1', task_id: 'M01-S01-T01', state: 'succeeded', workflow: 'build-test-review', pr },
      {
        run_id: 'r2',
        task_id: 'M01-S01-T02',
        state: 'succeeded',
        workflow: 'build-test-review',
        pr: { ...pr, pr_id: '8', state: 'open', merged_by: null, auto_merge_error: 'conflict: base moved' },
      },
      { run_id: 'r3', task_id: 'M01-S01-T02', state: 'failed', workflow: 'resolve-reviewed', error: 'tests failed\nlog' },
    ]
    const wrapper = mount(ChainPanel, { props: { chains: [chain({ state: 'finished', stop: 'failed', runs })] } })
    const [merged, open, failed] = wrapper.findAll('[data-test="chain-run"]')
    expect(merged!.get('[data-test="chain-run-pr"]').attributes('href')).toBe('https://example.test/pr/7')
    expect(merged!.get('[data-test="chain-run-pr"]').text()).toBe('PR #7 (sloučený)')
    expect(merged!.get('[data-test="chain-run-pr"]').attributes('target')).toBe('_blank')
    expect(merged!.get('[data-test="chain-run-review"]').attributes('href')).toBe('#/r/haifa/review/M01-S01-T01')
    expect(open!.get('[data-test="chain-run-pr"]').text()).toBe('PR #8 (otevřený)')
    expect(merged!.get('[data-test="chain-run-merged"]').text()).toBe('sloučil auto-merge')
    expect(open!.get('[data-test="chain-run-merge-error"]').text()).toBe('auto-merge nesloučil: conflict: base moved')
    expect(failed!.get('[data-test="chain-run-workflow"]').text()).toBe('resolve-reviewed')
    expect(failed!.find('[data-test="chain-run-pr"]').exists()).toBe(false)
    expect(failed!.get('[data-test="chain-run-error"]').text()).toBe('tests failed')
  })

  it('hides only an ended chain', async () => {
    const running = mount(ChainPanel, { props: { chains: [chain()] } })
    expect(running.find('[data-test="chain-dismiss"]').exists()).toBe(false)
    const ended = mount(ChainPanel, { props: { chains: [chain({ state: 'finished', stop: 'exhausted' })] } })
    await ended.get('[data-test="chain-dismiss"]').trigger('click')
    expect(ended.emitted('dismiss')).toEqual([['c1']])
    await ended.setProps({ dismissing: 'c1' })
    expect(ended.get('[data-test="chain-dismiss"]').attributes('disabled')).toBeDefined()
  })
})
