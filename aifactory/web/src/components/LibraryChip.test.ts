import { describe, expect, it, vi, afterEach } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import LibraryChip from './LibraryChip.vue'

function stubLibrary(exists: boolean) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, data: { exists }, error: null, warnings: [] }), { headers: { 'content-type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

enableAutoUnmount(afterEach)
afterEach(() => vi.unstubAllGlobals())

describe('LibraryChip', () => {
  it('links to the library when it exists', async () => {
    stubLibrary(true)
    const wrapper = mount(LibraryChip)
    await flushPromises()
    const chip = wrapper.get('[data-test="library-chip-ok"]')
    expect(chip.text()).toBe('')
    expect(chip.attributes('aria-label')).toContain('Knihovna OK')
    await chip.trigger('focusin')
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe(chip.attributes('aria-label'))
    await chip.trigger('focusout')
    expect(chip.attributes('href')).toBe('#/setup/library')
    wrapper.unmount()
  })

  it('offers to create the library when there is none', async () => {
    stubLibrary(false)
    const wrapper = mount(LibraryChip)
    await flushPromises()
    const chip = wrapper.get('[data-test="library-chip-missing"]')
    expect(chip.text()).toBe('')
    expect(chip.attributes('aria-label')).toContain('Založit knihovnu')
    await wrapper.get('[data-test="tip-anchor"]').trigger('mouseenter')
    expect(document.body.querySelector('[role="tooltip"]')?.textContent).toBe(chip.attributes('aria-label'))
    await wrapper.get('[data-test="tip-anchor"]').trigger('mouseleave')
    expect(chip.attributes('href')).toBe('#/setup/library')
    wrapper.unmount()
  })

  it('reloads after a factory change', async () => {
    const fetchMock = stubLibrary(false)
    mount(LibraryChip)
    await flushPromises()
    window.dispatchEvent(new Event('factory-applied'))
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
