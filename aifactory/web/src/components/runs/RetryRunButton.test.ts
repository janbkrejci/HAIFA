import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { hasUnsavedChanges } from '@/lib/leaveGuard'
import RetryRunButton from './RetryRunButton.vue'

afterEach(() => vi.unstubAllGlobals())

it('retains a guarded draft after a failed retry, including when collapsed, then clears on success', async () => {
  const fetchMock = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(
    new Response(JSON.stringify({ ok: true, data: { run_id: 'r2' }, error: null })),
  )
  vi.stubGlobal('fetch', fetchMock)
  const wrapper = mount(RetryRunButton, { props: { runId: 'r1' } })
  await wrapper.get('[data-test="retry-run"]').trigger('click')
  await wrapper.get('[data-test="retry-note"]').setValue('keep this')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(hasUnsavedChanges()).toBe(true)
  expect(wrapper.get('[data-test="retry-note"]').element).toHaveProperty('value', 'keep this')
  await wrapper.get('[data-test="retry-cancel"]').trigger('click')
  expect(hasUnsavedChanges()).toBe(true)
  await wrapper.get('[data-test="retry-run"]').trigger('click')
  await wrapper.get('form').trigger('submit')
  await flushPromises()
  expect(hasUnsavedChanges()).toBe(false)
  expect(wrapper.emitted('started')).toHaveLength(1)
  wrapper.unmount()
})
