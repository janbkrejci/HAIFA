import { describe, expect, it, vi, afterEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import LibraryChip from './LibraryChip.vue'

function stubLibrary(exists: boolean) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify({ ok: true, data: { exists }, error: null, warnings: [] }), { headers: { 'content-type': 'application/json' } }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => vi.unstubAllGlobals())

describe('LibraryChip', () => {
  it('links to the library when it exists', async () => {
    stubLibrary(true)
    const wrapper = mount(LibraryChip)
    await flushPromises()
    const chip = wrapper.get('[data-test="library-chip-ok"]')
    expect(chip.text()).toContain('Knihovna OK')
    expect(chip.attributes('href')).toBe('#/library')
    wrapper.unmount()
  })

  it('offers to create the library when there is none', async () => {
    stubLibrary(false)
    const wrapper = mount(LibraryChip)
    await flushPromises()
    const chip = wrapper.get('[data-test="library-chip-missing"]')
    expect(chip.text()).toContain('Založit knihovnu')
    expect(chip.attributes('href')).toBe('#/setup')
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
