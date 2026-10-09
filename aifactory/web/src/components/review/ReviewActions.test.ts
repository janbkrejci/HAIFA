import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ReviewActions from './ReviewActions.vue'
import { reviewDetail } from '@/test/reviewFixtures'
import { answerDialog, openDialog } from '@/test/modal'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('ReviewActions', () => {
  it('says that approve sends no approve review (OB3)', () => {
    const wrapper = mount(ReviewActions, { props: { detail: reviewDetail(), busy: false } })
    expect(wrapper.find('[data-test="ob3-note"]').text()).toContain('OB3')
  })

  it('approves after a confirm in the modal', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    const detail = reviewDetail()
    const wrapper = mount(ReviewActions, { props: { detail, busy: false }, attachTo: document.body })
    await wrapper.find('[data-test="approve"]').trigger('click')
    await flushPromises()
    const dialog = openDialog()
    expect(dialog?.textContent).toContain('Schválit a mergovat PR')
    expect(dialog?.querySelector('[data-test="confirm-message"]')?.textContent).toContain(detail.approve_note)
    await answerDialog(false)
    expect(wrapper.emitted('approve')).toBeUndefined()
    expect(openDialog()).toBeNull()
    await wrapper.find('[data-test="approve"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.emitted('approve')).toHaveLength(1)
    expect(openDialog()).toBeNull()
    expect(confirmSpy).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it('offers resolve and blocks approve on a conflict', () => {
    const detail = reviewDetail({
      mergeability: 'conflict',
      actions: { approve: false, return: true, resolve: true },
    })
    const wrapper = mount(ReviewActions, { props: { detail, busy: false } })
    expect(wrapper.find('[data-test="approve"]').attributes('disabled')).toBeDefined()
    const banner = wrapper.find('[data-test="conflict-banner"]')
    expect(banner.text()).toContain('nejde mergovat do main – „Vyřešit konflikt s base“ spustí')
    const resolve = banner.find('[data-test="resolve"]')
    expect(resolve.classes()).toContain('primary')
    expect(resolve.text()).toBe('Vyřešit konflikt s base')
    expect(resolve.attributes('disabled')).toBeUndefined()
  })

  it('offers a subdued resolve without a conflict', async () => {
    const wrapper = mount(ReviewActions, { props: { detail: reviewDetail(), busy: false } })
    expect(wrapper.find('[data-test="conflict-banner"]').exists()).toBe(false)
    const resolve = wrapper.find('[data-test="resolve"]')
    expect(resolve.text()).toBe('Dorovnat s base')
    await resolve.trigger('click')
    expect(wrapper.emitted('resolve')).toHaveLength(1)
  })

  it('returns only with a note, after a confirm in the modal', async () => {
    const wrapper = mount(ReviewActions, { props: { detail: reviewDetail(), busy: false }, attachTo: document.body })
    expect(wrapper.find('[data-test="return"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="return-note"]').setValue('  přidej test  ')
    expect(wrapper.find('[data-test="return"]').attributes('disabled')).toBeUndefined()
    await wrapper.find('[data-test="return"]').trigger('click')
    await flushPromises()
    const dialog = openDialog()
    expect(dialog?.textContent).toContain('Vrátit PR M01-S01-T01 agentovi')
    expect(dialog?.querySelector('[data-test="confirm-message"]')?.textContent).toContain('přidej test')
    await answerDialog(false)
    expect(wrapper.emitted('return')).toBeUndefined()
    await wrapper.find('[data-test="return"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.emitted('return')?.[0]).toEqual(['přidej test'])
    wrapper.unmount()
  })

  it('keeps the note until the parent says the return succeeded', async () => {
    const wrapper = mount(ReviewActions, { props: { detail: reviewDetail(), busy: false, returned: 0 } })
    const note = wrapper.find<HTMLTextAreaElement>('[data-test="return-note"]')
    await note.setValue('přidej test')
    await wrapper.setProps({ busy: true })
    await wrapper.setProps({ busy: false })
    expect(note.element.value).toBe('přidej test')
    await wrapper.setProps({ returned: 1 })
    expect(note.element.value).toBe('')
  })

  it('disables every action while a run is on the PR', () => {
    const detail = reviewDetail({
      mergeability: 'conflict',
      running_run: { run_id: 'r-run', workflow: 'resolve', started_at: '2026-01-01T11:00:00+00:00' },
    })
    const wrapper = mount(ReviewActions, { props: { detail, busy: false } })
    expect(wrapper.find('[data-test="running-info"] a').attributes('href')).toBe('#/r/haifa/runs/r-run')
    for (const name of ['approve', 'return', 'resolve', 'return-note']) {
      expect(wrapper.find(`[data-test="${name}"]`).attributes('disabled')).toBeDefined()
    }
  })
})
