// Helpers for the shared ConfirmDialog, which is teleported into <body>
// (VTU's wrapper.find does not see it).
import { flushPromises } from '@vue/test-utils'

export function openDialog(): HTMLElement | null {
  const all = document.body.querySelectorAll<HTMLElement>('[data-test="confirm-dialog"]')
  return all[all.length - 1] ?? null
}

/** Answers the open confirm dialog: Potvrdit (`ok`) or Zrušit. */
export async function answerDialog(ok: boolean): Promise<void> {
  await flushPromises()
  const dialog = openDialog()
  if (!dialog) throw new Error('confirm dialog is not open')
  const button = dialog.querySelector<HTMLButtonElement>(
    ok ? '[data-test="confirm-ok"]' : '[data-test="confirm-cancel"]',
  )
  if (!button) throw new Error('confirm dialog has no answer button')
  button.click()
  await flushPromises()
}
