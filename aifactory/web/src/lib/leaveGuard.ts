// Guard against leaving a form with unsaved changes. A form registers a dirty check;
// the router asks before a hash change (a link, the guide, another task, the back
// button) and the browser asks before a reload or close. Bind `leaveDialog` to the
// one <ConfirmDialog> in App.vue.
import { getCurrentInstance, onBeforeUnmount } from 'vue'
import { useConfirm } from './confirm'

type DirtyCheck = () => boolean

const checks = new Set<DirtyCheck>()

/** True when any registered form has unsaved changes. */
export function hasUnsavedChanges(): boolean {
  for (const check of checks) if (check()) return true
  return false
}

/** Registers a dirty check; returns its removal. */
export function registerUnsaved(check: DirtyCheck): () => void {
  checks.add(check)
  return () => {
    checks.delete(check)
  }
}

/** Registers a dirty check for the lifetime of the calling component. */
export function useUnsavedGuard(check: DirtyCheck): void {
  const remove = registerUnsaved(check)
  if (getCurrentInstance()) onBeforeUnmount(remove)
}

const confirmer = useConfirm()

/** The leave question: bind it to a ConfirmDialog. */
export const leaveDialog = confirmer.dialog
export const confirmLeave = confirmer.confirm
export const cancelLeave = confirmer.cancel

/** Asks whether to drop the unsaved changes; resolves true when the user discards them. */
export function askDiscard(): Promise<boolean> {
  return confirmer.ask({
    title: 'Zahodit neuložené změny?',
    message: 'Rozepsané změny nejsou uložené. Když odejdeš, přijdeš o ně.',
    confirmLabel: 'Zahodit změny',
    cancelLabel: 'Zůstat',
    tone: 'danger',
  })
}

/** The hash the app shows; a blocked change returns the URL to it. */
let acceptedHash = window.location.hash
/** A hash the user already agreed to leave for. */
let allowedHash: string | null = null

/** The router accepted (and maybe redirected) the current hash. */
export function acceptHash(): void {
  acceptedHash = window.location.hash
}

/**
 * Decides a hash change: true lets the router follow it. With unsaved changes the URL
 * goes back to the shown screen and the question is asked; on "Zahodit změny" the
 * navigation is repeated and passes.
 */
export function allowHashChange(): boolean {
  const target = window.location.hash
  if (target === acceptedHash) return true
  if (allowedHash === target) {
    allowedHash = null
    return true
  }
  if (!hasUnsavedChanges()) return true
  window.history.replaceState(null, '', acceptedHash || `${window.location.pathname}${window.location.search}`)
  void askDiscard().then((ok) => {
    if (!ok) return
    allowedHash = target
    window.location.hash = target
  })
  return false
}

/** Tests: forget forms a test left mounted and any open question. */
export function resetUnsavedForTests(): void {
  checks.clear()
  allowedHash = null
  confirmer.cancel()
}

window.addEventListener('beforeunload', (event) => {
  if (!hasUnsavedChanges()) return
  event.preventDefault()
  event.returnValue = ''
})
