import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoCard from './RepoCard.vue'
import type { OverviewRepo } from '@/lib/api'
import { factory, failed, mergedOutside, operation, repo, review, running, tasks } from '@/test/overviewFixtures'

const api = vi.hoisted(() => ({ backlogSync: vi.fn(), controlStart: vi.fn(), controlPause: vi.fn() }))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))

enableAutoUnmount(afterEach)

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
})

function mountWith(r: OverviewRepo) {
  return mount(RepoCard, { props: { repo: r, now: Date.parse('2026-10-06T10:00:00Z') }, attachTo: document.body })
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('RepoCard pull requests', () => {
  it('shows PRs waiting for review and PRs waiting for auto-merge in separate sections', () => {
    const card = mountWith(
      repo('a', {
        review: [review({ task_id: 'M01-S01-T02', pr_id: '42' })],
        approved: [review({ task_id: 'approved', pr_id: '44' })],
        automerge: [review({ task_id: 'M01-S01-T05', pr_id: '45' })],
      }),
    )
    const sections = card.findAll('section.group h3').map((h) => h.text())
    expect(sections).toEqual(['Čeká na review', 'Schváleno, čeká na CI', 'Čeká na automerge PR'])
    expect(card.findAll('[data-test="row-review"]').map((r) => r.attributes('data-task'))).toEqual(['M01-S01-T02'])
    expect(card.get('[data-test="approved"] [data-test="row-approved"]').attributes('href')).toBe('#/r/a/review/approved')
    const merge = card.get('[data-test="automerge"]')
    const rows = merge.findAll('[data-test="row-automerge"]')
    expect(rows.map((r) => r.attributes('data-task'))).toEqual(['M01-S01-T05'])
    expect(rows[0].attributes('href')).toBe('#/r/a/review/M01-S01-T05')
    expect(rows[0].text()).toContain('PR #45')
  })

  it('has no auto-merge section without such a PR', () => {
    const card = mountWith(repo('a', { review: [review()] }))
    expect(card.find('[data-test="approved"]').exists()).toBe(false)
    expect(card.find('[data-test="automerge"]').exists()).toBe(false)
    expect(card.text()).not.toContain('Čeká na automerge PR')
  })
})

describe('RepoCard layout', () => {
  const busy = () =>
    repo('a', {
      running: [running()],
      tasks: tasks({ running: 1, ready: 1 }),
      factory: factory({ can_start: true, ready: 1, running: 1 }),
      warnings: ['pozor'],
      merged_outside: [mergedOutside()],
    })

  it('puts the icon buttons next to the menu in the header', () => {
    const head = mountWith(busy()).get('.card-head')
    const tools = head.get('.card-tools')
    expect(tools.findAll('button[data-test^="factory-"]').map((b) => b.attributes('data-test'))).toEqual([
      'factory-start',
      'factory-pause',
      'factory-stop',
    ])
    for (const b of tools.findAll('button[data-test^="factory-"]')) expect(b.text()).toBe('')
    expect(tools.find('[data-test="repo-menu"]').exists()).toBe(true)
  })

  it('keeps the last activity as the last element of the card', () => {
    const card = mountWith(busy()).get('[data-test="overview-card"]').element
    expect(card.lastElementChild?.getAttribute('data-test')).toBe('last-activity')
  })

  it('shows the message of a button under the header and emits changed', async () => {
    api.controlStart.mockResolvedValue({
      max_parallel_runs: 2,
      running: 0,
      free_slots: 2,
      started: [{ task_id: 'T1', run_id: 'r1' }],
      skipped: [],
    })
    const wrapper = mountWith(busy())
    await wrapper.get('[data-test="factory-start"]').trigger('click')
    await flushPromises()
    expect(api.controlStart).toHaveBeenCalledWith('a')
    expect(wrapper.get('[data-test="factory-controls"] [data-test="factory-start-message"]').text()).toBe('Spuštěno 1 běh')
    expect(wrapper.emitted('changed')).toHaveLength(1)
  })

  it('shows the error of a button under the header', async () => {
    api.controlPause.mockRejectedValue(new Error('boom'))
    const wrapper = mountWith(busy())
    await wrapper.get('[data-test="factory-pause"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="factory-controls"] [data-test="factory-control-error"]').text()).toContain('boom')
    expect(wrapper.find('[data-test="factory-start-message"]').exists()).toBe(false)
  })

  it('shows the path only in the tooltip of the name', async () => {
    const wrapper = mountWith(busy())
    expect(wrapper.text()).not.toContain('/work/a')
    await wrapper.get('[data-test="card-name"]').trigger('focusin')
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent?.trim()).toBe('/work/a')
  })
})

describe('RepoCard merged outside factory', () => {
  it('has no section without merged tasks', () => {
    expect(mountWith(repo('a')).find('[data-test="merged-outside"]').exists()).toBe(false)
  })

  it('lists the tasks with a link to the PR and opens the sync PR on request', async () => {
    api.backlogSync.mockResolvedValue({
      url: 'https://example.test/pr/38',
      created: true,
      updated: false,
      tasks: [{ task_id: 'M01-S01-T04' }],
    })
    const wrapper = mountWith(repo('a', { merged_outside: [mergedOutside()] }))
    const row = wrapper.find('[data-test="row-merged-outside"]')
    expect(row.attributes('data-task')).toBe('M01-S01-T04')
    expect(row.attributes('href')).toBe('https://example.test/pr/37')
    expect(row.attributes('target')).toBe('_blank')
    expect(row.text()).toContain('Merged by hand')
    expect(api.backlogSync).not.toHaveBeenCalled()

    await wrapper.find('[data-test="sync-open"]').trigger('click')
    expect(api.backlogSync).toHaveBeenCalledWith('a')
    await flushPromises()
    expect(wrapper.emitted('changed')).toHaveLength(1)
    expect(wrapper.find('[data-test="sync-open"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="sync-pr-link"]').attributes('href')).toBe('https://example.test/pr/38')
  })

  it('shows the error of a failed sync', async () => {
    api.backlogSync.mockRejectedValue(new Error('sync failed'))
    const wrapper = mountWith(repo('a', { merged_outside: [mergedOutside()] }))
    await wrapper.find('[data-test="sync-open"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="sync-error"]').text()).toContain('sync failed')
    expect(wrapper.find('[data-test="sync-open"]').exists()).toBe(true)
  })

  it('links the open sync PR instead of the button', () => {
    const wrapper = mountWith(
      repo('a', {
        merged_outside: [mergedOutside()],
        sync_pr: { url: 'https://example.test/pr/40', branch: 'factory-sync/1', tasks: ['M01-S01-T04'] },
      }),
    )
    expect(wrapper.find('[data-test="sync-open"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="sync-pr-link"]').attributes('href')).toBe('https://example.test/pr/40')
  })
})

describe('RepoCard automatic actions', () => {
  it('lists what the factory did by itself after a failure, each row a link to the run', () => {
    const card = mountWith(
      repo('a', {
        auto_actions: [
          {
            at: '2026-10-06T09:58:00Z',
            action: 'fallback',
            failure_kind: 'quota',
            task_id: 'M01-S01-T02',
            run_id: 'r-quota',
            ok: true,
            text: 'Factory pokračovala na Claude Code po vyčerpání kvóty Codexu',
          },
          {
            at: '2026-10-06T09:50:00Z',
            action: 'retry',
            failure_kind: 'process_gone',
            task_id: 'M01-S01-T03',
            run_id: 'r-gone',
            ok: false,
            text: 'Factory zopakovala běh r-gone po pádu procesu; opakování selhalo',
          },
        ],
      }),
    )
    expect(card.findAll('section.group h3').map((h) => h.text())).toContain('Factory zasáhla sama')
    const rows = card.findAll('[data-test="row-auto-action"]')
    expect(rows.map((r) => r.attributes('data-action'))).toEqual(['fallback', 'retry'])
    expect(rows[0].text()).toContain('Factory pokračovala na Claude Code po vyčerpání kvóty Codexu')
    expect(rows[0].attributes('href')).toBe('#/r/a/runs/r-quota')
    expect(rows[1].classes()).toContain('failed')
  })

  it('has no section without automatic actions', () => {
    expect(mountWith(repo('a')).text()).not.toContain('Factory zasáhla sama')
  })
})


describe('RepoCard projects', () => {
  const projects = [
    { id: 'A', title: 'Alpha', tasks: tasks({ running: 1, ready: 2 }) },
    { id: 'B', title: 'Beta', tasks: tasks({ 'in review': 1, 'awaiting merge': 1 }) },
  ]
  it.each(['merged_outside', 'auto_actions'] as const)(
    'renders unassigned %s once outside projects without an empty section', (list) => {
      const card = mount(RepoCard, { props: {
        repo: repo('multi', {
          projects,
          merged_outside: list === 'merged_outside' ? [mergedOutside({ project: null })] : [],
          auto_actions: list === 'auto_actions' ? [{
            project: null, at: '2026-10-06T09:58:00Z', action: 'retry',
            failure_kind: 'process_gone', task_id: 'T01', run_id: 'run-1',
            ok: true, text: 'Factory zopakovala běh',
          }] : [],
        }),
        now: Date.now(), byProject: true,
      } })

      expect(card.findAll('[data-test="project-section"]')).toHaveLength(2)
      expect(card.text()).not.toContain('Bez projektu')
      const row = list === 'merged_outside' ? 'row-merged-outside' : 'row-auto-action'
      expect(card.findAll(`[data-test="${row}"]`)).toHaveLength(1)
      expect(card.find(`[data-test="project-section"] [data-test="${row}"]`).exists()).toBe(false)
    },
  )

  it('keeps merged-outside PRs and working sync controls once per repo across grouping modes', async () => {
    api.backlogSync.mockResolvedValue({
      url: 'https://example.test/pr/38', created: true, updated: false,
      tasks: [{ task_id: 'A-T04' }, { task_id: 'B-T04' }],
    })
    const card = mount(RepoCard, { props: {
      repo: repo('multi', {
        projects,
        merged_outside: [
          mergedOutside({ project: 'A', task_id: 'A-T04', pr_id: '37', url: 'https://example.test/pr/37' }),
          mergedOutside({ project: 'B', task_id: 'B-T04', pr_id: '39', url: 'https://example.test/pr/39' }),
        ],
      }),
      now: Date.now(), byProject: true,
    } })
    expect(card.findAll('[data-test="project-section"]')).toHaveLength(2)
    const assertMerged = () => {
      expect(card.findAll('[data-test="merged-outside"]')).toHaveLength(1)
      const rows = card.findAll('[data-test="row-merged-outside"]')
      expect(rows.map((r) => r.attributes('data-task'))).toEqual(['A-T04', 'B-T04'])
      expect(rows.map((r) => r.attributes('href'))).toEqual(['https://example.test/pr/37', 'https://example.test/pr/39'])
      expect(card.find('[data-test="project-section"] [data-test="merged-outside"]').exists()).toBe(false)
    }
    assertMerged()
    expect(card.findAll('[data-test="sync-open"]')).toHaveLength(1)
    await card.get('[data-test="sync-open"]').trigger('click')
    await flushPromises()
    expect(api.backlogSync).toHaveBeenCalledExactlyOnceWith('multi')
    expect(card.findAll('[data-test="sync-pr-link"]')).toHaveLength(1)
    expect(card.get('[data-test="sync-pr-link"]').attributes('href')).toBe('https://example.test/pr/38')
    expect(card.emitted('changed')).toHaveLength(1)

    await card.setProps({ byProject: false })
    expect(card.find('[data-test="project-section"]').exists()).toBe(false)
    assertMerged()
    expect(card.findAll('[data-test="sync-pr-link"]')).toHaveLength(1)
    expect(card.get('[data-test="sync-pr-link"]').attributes('href')).toBe('https://example.test/pr/38')
  })

  it('shows project rows and coloured chips, then restores the summary', async () => {
    const card = mount(RepoCard, { props: { repo: repo('multi', {
      projects, tasks: tasks({ running: 1, ready: 2, 'in review': 1, 'awaiting merge': 1 }),
      running: [running({ project: 'A' })], review: [review({ project: 'B' })],
      automerge: [review({ project: 'B', task_id: 'merge' })],
      failed: [failed({ project: 'A' })], factory: factory({ running: 1 }),
    }), now: Date.now(), byProject: true } })
    const sections = card.findAll('[data-test="project-section"]')
    expect(sections).toHaveLength(2)
    expect(sections[0].text()).toContain('Alpha')
    expect(sections[0].findAll('[data-test="row-running"]')).toHaveLength(1)
    expect(sections[0].findAll('[data-test="row-failed"]')).toHaveLength(1)
    expect(sections[0].find('[data-test="row-review"]').exists()).toBe(false)
    expect(sections[0].get('[data-state="ready"]').classes()).toContain('state-ready')
    expect(sections[0].get('[data-state="ready"]').text()).toContain('2')
    expect(sections[1].text()).toContain('Beta')
    expect(sections[1].findAll('[data-test="row-review"]')).toHaveLength(1)
    expect(sections[1].findAll('[data-test="row-automerge"]')).toHaveLength(1)
    expect(sections[1].get('[data-state="in review"]').classes()).toContain('state-in-review')
    expect(card.findAll('[data-test="factory-slots"]')).toHaveLength(1)
    await card.setProps({ byProject: false })
    expect(card.find('[data-test="project-section"]').exists()).toBe(false)
    expect(card.findAll('[data-test="task-summary"]')).toHaveLength(1)
    expect(card.findAll('[data-test="row-running"]')).toHaveLength(1)
    expect(card.findAll('[data-test="row-review"]')).toHaveLength(1)
  })

  it('shows unassigned work in its own section', () => {
    const card = mount(RepoCard, { props: { repo: repo('multi', {
      projects, running: [running({ project: null })],
      failed: [failed({ run_id: 'ended', project: null })],
    }), now: Date.now(), byProject: true } })
    const sections = card.findAll('[data-test="project-section"]')
    expect(sections).toHaveLength(3)
    expect(sections[2].text()).toContain('Bez projektu')
    expect(sections[2].findAll('[data-test="row-running"]')).toHaveLength(1)
    expect(sections[2].findAll('[data-test="row-failed"]')).toHaveLength(1)
    expect(sections[0].find('[data-test="row-running"]').exists()).toBe(false)
  })

  it('keeps one-project repos in aggregate mode', async () => {
    const card = mount(RepoCard, { props: { repo: repo('single', { projects: projects.slice(0, 1), tasks: tasks({ ready: 2 }) }), now: Date.now(), byProject: true } })
    expect(card.find('[data-test="project-section"]').exists()).toBe(false)
    const before = card.text()
    await card.setProps({ byProject: false })
    expect(card.text()).toBe(before)
  })
})


describe('RepoCard pending operations', () => {
  it('links multiple pending tasks and replaces an operation with the claimed run', async () => {
    const first = operation('operation-1', { task_id: 'T1', task_title: 'First' })
    const second = operation('operation-2', { task_id: 'T2', task_title: 'Second', workflow: 'publish' })
    const card = mountWith(repo('a', { running: [first, second] }))
    const rows = () => card.findAll('[data-test="row-running"]')
    expect(rows().map((r) => r.attributes('data-operation'))).toEqual(['operation-1', 'operation-2'])
    expect(rows().map((r) => r.attributes('href'))).toEqual(['#/r/a/backlog/T1', '#/r/a/backlog/T2'])
    const secondElement = rows()[1].element
    const claimed = running({ run_id: 'claimed-1', task_id: 'T1', task_title: 'First', pause: 'paused' })
    await card.setProps({ repo: repo('a', { running: [second, claimed] }) })
    expect(rows()[0].element).toBe(secondElement)
    expect(rows()[0].attributes('href')).toBe('#/r/a/backlog/T2')
    expect(rows()[1].attributes('data-run')).toBe('claimed-1')
    expect(rows()[1].attributes('data-operation')).toBeUndefined()
    expect(rows()[1].attributes('href')).toBe('#/r/a/runs/claimed-1')
    expect(rows()[1].get('[data-test="row-phase"]').text()).toBe('build · pokus 2')
    expect(rows()[1].get('[data-test="row-cost"]').text()).toContain('1.25')
    expect(card.find('[data-test="factory-resume"]').exists()).toBe(true)
  })
})
