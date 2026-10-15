import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoCard from './RepoCard.vue'
import type { OverviewRepo } from '@/lib/api'
import { factory, mergedOutside, repo, running, tasks } from '@/test/overviewFixtures'

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
