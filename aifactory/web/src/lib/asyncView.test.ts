import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { asyncView } from './asyncView'
import { deferred } from '@/test/deferred'

afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

it('loads on mount, shows progress, then displays the resolved screen', async () => {
  vi.useFakeTimers()
  const pending = deferred<ReturnType<typeof defineComponent>>()
  const loader = vi.fn(() => pending.promise)
  const screen = asyncView(loader)
  expect(loader).not.toHaveBeenCalled()
  const wrapper = mount({ components: { Screen: screen }, template: '<Screen />' })
  await vi.advanceTimersByTimeAsync(150)
  expect(wrapper.get('[role="status"]').text()).toBe('Načítám…')
  pending.resolve(defineComponent({ template: '<h1>Ready</h1>' }))
  await flushPromises()
  expect(wrapper.get('h1').text()).toBe('Ready')
  wrapper.unmount()
})

it('shows a recovery action when the screen chunk cannot load', async () => {
  vi.spyOn(console, 'warn').mockImplementation(() => {})
  vi.spyOn(console, 'error').mockImplementation(() => {})
  const reload = vi.spyOn(window.location, 'reload').mockImplementation(() => {})
  const screen = asyncView(async () => { throw new Error('offline') })
  const wrapper = mount({ components: { Screen: screen }, template: '<Screen />' })
  await flushPromises()
  expect(wrapper.get('[role="alert"]').text()).toContain('Obrazovku se nepodařilo načíst')
  await wrapper.get('button').trigger('click')
  expect(reload).toHaveBeenCalledOnce()
  wrapper.unmount()
})
