// Global test setup (vite.config.ts test.setupFiles): every test starts on a screen of repo
// `haifa`, so repo-scoped requests go to /api/repos/haifa/… A test may set its own hash.
import { beforeEach } from 'vitest'

export const TEST_REPO = 'haifa'
export const TEST_HASH = `#/r/${TEST_REPO}/backlog`

// before the test file imports the router, which reads the hash once at load
window.location.hash = TEST_HASH

beforeEach(() => {
  window.location.hash = TEST_HASH
  // happy-dom fires hashchange on a timer; the router's refs follow the hash right away
  window.dispatchEvent(new HashChangeEvent('hashchange'))
})
