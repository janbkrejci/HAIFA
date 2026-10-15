import { describe, expect, it } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { TEST_HASH } from '@/test/setup'
import { usePage } from './router'
import { cancelLeave, confirmLeave, hasUnsavedChanges, leaveDialog, registerUnsaved } from './leaveGuard'

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

describe('leave guard', () => {
  it('lets the router follow a hash change without unsaved changes', () => {
    go('#/guide')
    expect(leaveDialog.open).toBe(false)
    expect(usePage().value).toBe('guide')
  })

  it('keeps the screen and asks before leaving unsaved changes', () => {
    registerUnsaved(() => true)
    go('#/guide')
    expect(leaveDialog.open).toBe(true)
    expect(window.location.hash).toBe(TEST_HASH)
    expect(usePage().value).toBe('repo')
  })

  it('stays on "Zůstat"', async () => {
    registerUnsaved(() => true)
    go('#/guide')
    cancelLeave()
    await flushPromises()
    expect(window.location.hash).toBe(TEST_HASH)
    expect(usePage().value).toBe('repo')
  })

  it('leaves on "Zahodit změny"', async () => {
    registerUnsaved(() => true)
    go('#/guide')
    confirmLeave()
    await flushPromises()
    window.dispatchEvent(new HashChangeEvent('hashchange'))
    expect(window.location.hash).toBe('#/guide')
    expect(usePage().value).toBe('guide')
    expect(leaveDialog.open).toBe(false)
  })

  it('forgets a form once it is removed', () => {
    const remove = registerUnsaved(() => true)
    expect(hasUnsavedChanges()).toBe(true)
    remove()
    expect(hasUnsavedChanges()).toBe(false)
  })

  it('asks the browser before a reload with unsaved changes', () => {
    registerUnsaved(() => true)
    const event = new Event('beforeunload', { cancelable: true })
    window.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(true)
  })
})
