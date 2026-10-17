import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import FollowUpDialog from './FollowUpDialog.vue'
import { ApiError } from '@/lib/api'

const api = vi.hoisted(() => ({ postApi: vi.fn(), getApi: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({ ...(await original<object>()), ...api }))

const RESULT = { action: 'follow-up', changed: true, path: 'x.md', task: { id: 'P-T02' }, issues: [], commit: null, run: null, pending: false }

function dialog() {
  return mount(FollowUpDialog, { props: { taskId: 'P-T01', taskTitle: 'Schema' } })
}

const COMMIT = { committed: true, commit: 'abc', base: 'main', paths: ['x.md'], pushed: false }

beforeEach(() => {
  api.postApi.mockReset().mockImplementation(async (path: string) => (path === '/backlog/commit' ? COMMIT : RESULT))
})

afterEach(() => {
  document.body.innerHTML = ''
})

describe('FollowUpDialog', () => {
  it('has the body, an optional title and Spustit hned checked by default', () => {
    const wrapper = dialog()
    expect(wrapper.text()).toContain('Co změnit, předělat nebo dodělat')
    expect((wrapper.get('[data-test="follow-up-run"]').element as HTMLInputElement).checked).toBe(true)
    expect(wrapper.get('[data-test="follow-up-title"]').attributes('placeholder')).toBe('Navazuje na P-T01: Schema')
    expect(wrapper.get('[data-test="follow-up-submit"]').attributes('disabled')).toBeDefined()
  })

  it('with Spustit hned leaves the commit to the server', async () => {
    api.postApi.mockReset().mockResolvedValue({ ...RESULT, commit: COMMIT, pending: true })
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-body"]').setValue('x')
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('created')).toHaveLength(1)
  })

  it('sends body, title and run and emits the result', async () => {
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-body"]').setValue('  Dodělat docs.  ')
    await wrapper.get('[data-test="follow-up-title"]').setValue('Docs')
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/tasks/P-T01/follow-up', { body: 'Dodělat docs.', title: 'Docs', run: true })
    expect(wrapper.emitted('created')?.[0]?.[0]).toMatchObject({ task: { id: 'P-T02' } })
  })

  it('creates without a run when Spustit hned is unchecked', async () => {
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-body"]').setValue('x')
    await wrapper.get('[data-test="follow-up-run"]').setValue(false)
    expect(wrapper.get('[data-test="follow-up-submit"]').text()).toBe('Založit')
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(api.postApi).toHaveBeenCalledWith('/backlog/tasks/P-T01/follow-up', { body: 'x', run: false })
    // without the run the dialog commits the backlog itself
    expect(api.postApi).toHaveBeenLastCalledWith('/backlog/commit', { message: 'backlog: P-T02 follows P-T01' })
    expect(wrapper.emitted('created')).toEqual([[{ ...RESULT, commit: COMMIT }]])
  })

  it('a failed commit keeps the written task and offers to open it instead of creating it again', async () => {
    api.postApi.mockReset().mockImplementation(async (path: string) => {
      if (path === '/backlog/commit') throw new ApiError('commit_failed', 'Hlavní checkout není na base.')
      return RESULT
    })
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-body"]').setValue('x')
    await wrapper.get('[data-test="follow-up-run"]').setValue(false)
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Hlavní checkout není na base.')
    expect(wrapper.find('[data-test="follow-up-submit"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="follow-up-uncommitted"]').text()).toContain('P-T02')
    await wrapper.get('[data-test="follow-up-open"]').trigger('click')
    expect(wrapper.emitted('created')).toEqual([[RESULT]])
  })

  it('shows an API error and stays open', async () => {
    api.postApi.mockReset().mockRejectedValue(new ApiError('not_done', 'Task není hotový.'))
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-body"]').setValue('x')
    await wrapper.get('[data-test="follow-up-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Task není hotový.')
    expect(wrapper.emitted('created')).toBeUndefined()
  })

  it('cancels', async () => {
    const wrapper = dialog()
    await wrapper.get('[data-test="follow-up-cancel"]').trigger('click')
    expect(wrapper.emitted('cancel')).toEqual([[]])
  })
})
