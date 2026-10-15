import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import RepoCard from './RepoCard.vue'
import type { OverviewRepo } from '@/lib/api'
import { mergedOutside, repo } from '@/test/overviewFixtures'

const api = vi.hoisted(() => ({ backlogSync: vi.fn() }))
vi.mock('@/lib/api', async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }))

enableAutoUnmount(afterEach)

beforeEach(() => {
  api.backlogSync.mockReset()
})

function mountWith(r: OverviewRepo) {
  return mount(RepoCard, { props: { repo: r, now: Date.parse('2026-10-06T10:00:00Z') } })
}

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
