import { describe, expect, it } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { answerDialog } from '@/test/modal'
import ReviewDetail from './ReviewDetail.vue'
import { reviewDetail, taskPr } from '@/test/reviewFixtures'

const SECTIONS = ['Popis PR', 'Běhy', 'Gates a testy', 'Verdikt revieweru', 'Diff']

async function openSection(wrapper: VueWrapper, title: string) {
  const head = wrapper.findAll('button.dsec-head').find((b) => b.find('.dsec-title').text() === title)
  if (!head) throw new Error(`section ${title} not found`)
  await head.trigger('click')
}

async function openAll(wrapper: VueWrapper) {
  for (const title of SECTIONS) await openSection(wrapper, title)
  for (const head of wrapper.findAll('[data-test="diff-file-section"] button.dsec-head')) await head.trigger('click')
}

describe('ReviewDetail', () => {
  it('starts with every section collapsed and the actions visible on top', () => {
    const wrapper = mount(ReviewDetail, { props: { detail: reviewDetail(), busy: false } })
    expect(wrapper.findAll('.dsec')).toHaveLength(SECTIONS.length)
    expect(wrapper.findAll('.dsec-body')).toHaveLength(0)
    for (const t of ['pr-body', 'run-link', 'check', 'verdict-state', 'diff-stat']) {
      expect(wrapper.find(`[data-test="${t}"]`).exists()).toBe(false)
    }
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="return-note"]').exists()).toBe(true)
    const html = wrapper.html()
    expect(html.indexOf('data-test="actions"')).toBeLessThan(html.indexOf('class="dsec"'))
  })

  it('collapses again when another PR is shown, not on a refresh of the same PR', async () => {
    const wrapper = mount(ReviewDetail, { props: { detail: reviewDetail(), busy: false } })
    await openSection(wrapper, 'Popis PR')
    await openSection(wrapper, 'Diff')
    await wrapper.find('[data-test="diff-file-section"] button.dsec-head').trigger('click')
    expect(wrapper.findAll('[data-test="diff-file"]')).toHaveLength(1)

    await wrapper.setProps({ detail: reviewDetail({ cost: 9 }) })
    expect(wrapper.find('[data-test="pr-body"]').exists()).toBe(true)
    expect(wrapper.findAll('[data-test="diff-file"]')).toHaveLength(1)

    await wrapper.setProps({ detail: reviewDetail({ task_id: 'M09-S01-T01' }) })
    expect(wrapper.findAll('.dsec-body')).toHaveLength(0)
    await openSection(wrapper, 'Diff')
    expect(wrapper.findAll('[data-test="diff-file-section"]')).toHaveLength(2)
    expect(wrapper.findAll('[data-test="diff-file"]')).toHaveLength(0)
  })

  it('shows the body, runs, checks, verdict and diff', async () => {
    const wrapper = mount(ReviewDetail, { props: { detail: reviewDetail(), busy: false } })
    await openAll(wrapper)
    expect(wrapper.find('[data-test="pr-body"] h2').text()).toBe('Zadání')
    expect(wrapper.find('[data-test="owner"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('vlastník')
    expect(wrapper.find('[data-test="run-link"]').attributes('href')).toBe('#/r/haifa/runs/r-ok')
    const checks = wrapper.findAll('[data-test="check"]')
    expect(checks).toHaveLength(2)
    expect(checks[0].text()).toContain('artifacts_exist')
    expect(checks[1].classes()).toContain('fail')
    expect(wrapper.find('[data-test="verdict-state"]').text()).toBe('neschváleno')
    expect(wrapper.find('[data-test="blocking"]').text()).toContain('přidej test loaderu')
    expect(wrapper.find('[data-test="finding"]').text()).toContain('Loader čte YAML')
    expect(wrapper.findAll('[data-test="diff-file"]')).toHaveLength(2)
    expect(wrapper.find('[data-test="ob3-note"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="pr-link"]').attributes('href')).toBe('https://example.test/pr/7')
  })

  it('handles no checks and no verdict', async () => {
    const wrapper = mount(ReviewDetail, {
      props: { detail: reviewDetail({ checks: [], review: null }), busy: false },
    })
    await openSection(wrapper, 'Gates a testy')
    await openSection(wrapper, 'Verdikt revieweru')
    expect(wrapper.find('[data-test="no-checks"]').text()).toBe('Gates ani testy neběžely')
    expect(wrapper.find('[data-test="no-verdict"]').text()).toBe('Review neběželo')
  })

  it('forwards actions', async () => {
    const wrapper = mount(ReviewDetail, { props: { detail: reviewDetail(), busy: false }, attachTo: document.body })
    await wrapper.find('[data-test="resolve"]').trigger('click')
    expect(wrapper.emitted('resolve')).toHaveLength(1)
    await wrapper.find('[data-test="return-note"]').setValue('oprav')
    await wrapper.find('[data-test="return"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.emitted('return')?.[0]).toEqual(['oprav'])
    wrapper.unmount()
  })

  it('shows the task in the header as "ID Název"', () => {
    const wrapper = mount(ReviewDetail, {
      props: { detail: reviewDetail({ task_id: 'M01-S01-T02', task_title: 'Loader' }), busy: false },
    })
    expect(wrapper.find('[data-test="task-label"]').text()).toBe('M01-S01-T02 Loader')
    const bare = mount(ReviewDetail, { props: { detail: reviewDetail({ task_title: null }), busy: false } })
    expect(bare.find('[data-test="task-label"]').text()).toBe('M01-S01-T01')
  })

  it('is read only for a merged or closed PR', () => {
    const none = { approve: false, return: false, resolve: false }
    for (const state of ['merged', 'closed'] as const) {
      const wrapper = mount(ReviewDetail, {
        props: {
          detail: reviewDetail({
            provider_state: state,
            mergeability: 'conflict',
            awaiting_review: false,
            actions: none,
            pr: taskPr({ state, merged_at: state === 'merged' ? '2026-01-02T09:00:00+00:00' : null }),
          }),
          busy: false,
        },
      })
      const note = wrapper.find('[data-test="read-only"]')
      expect(note.exists()).toBe(true)
      expect(note.text()).toContain(state === 'merged' ? 'sloučeno' : 'zavřeno')
      for (const t of ['approve', 'return', 'resolve', 'return-note', 'conflict-banner']) {
        expect(wrapper.find(`[data-test="${t}"]`).exists()).toBe(false)
      }
      expect(wrapper.findAll('button').map((b) => b.text())).not.toContain('Schválit')
    }
  })

  it('says a PR was merged by auto-merge, and why auto-merge left one open', () => {
    const merged = mount(ReviewDetail, {
      props: {
        detail: reviewDetail({
          provider_state: 'merged',
          actions: { approve: false, return: false, resolve: false },
          pr: taskPr({ state: 'merged', merged_by: 'auto-merge', merged_at: '2026-01-02T09:00:00+00:00' }),
        }),
        busy: false,
      },
    })
    expect(merged.find('[data-test="merged-by-auto"]').text()).toBe('Sloučil auto-merge')
    expect(merged.find('[data-test="auto-merge-error"]').exists()).toBe(false)

    const byOperator = mount(ReviewDetail, {
      props: {
        detail: reviewDetail({
          provider_state: 'merged',
          actions: { approve: false, return: false, resolve: false },
          pr: taskPr({ state: 'merged', merged_by: 'operator' }),
        }),
        busy: false,
      },
    })
    expect(byOperator.find('[data-test="merged-by-auto"]').exists()).toBe(false)

    const open = mount(ReviewDetail, {
      props: {
        detail: reviewDetail({ pr: taskPr({ auto_merge_error: 'no_review_phase: workflow plan-commit' }) }),
        busy: false,
      },
    })
    expect(open.find('[data-test="auto-merge-error"]').text()).toContain('no_review_phase')
    expect(open.find('[data-test="approve"]').exists()).toBe(true)
  })

  it('keeps the actions of an open PR', () => {
    const wrapper = mount(ReviewDetail, { props: { detail: reviewDetail(), busy: false } })
    expect(wrapper.find('[data-test="read-only"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="approve"]').exists()).toBe(true)
  })
})
