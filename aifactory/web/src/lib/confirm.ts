// Promise API over the shared ConfirmDialog: `await ask({...})` resolves true on
// confirm and false on cancel. Bind `dialog` to <ConfirmDialog v-bind="dialog" …>.
import { reactive } from 'vue'

export type ConfirmTone = 'default' | 'danger'

export interface ConfirmOptions {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: ConfirmTone
}

const DEFAULTS = { message: '', confirmLabel: 'Potvrdit', cancelLabel: 'Zrušit', tone: 'default' as ConfirmTone }

export function useConfirm() {
  const dialog = reactive({ open: false, title: '', ...DEFAULTS })
  let resolver: ((ok: boolean) => void) | null = null

  function settle(ok: boolean) {
    dialog.open = false
    const resolve = resolver
    resolver = null
    resolve?.(ok)
  }

  function ask(opts: ConfirmOptions): Promise<boolean> {
    settle(false) // an earlier question still open counts as cancelled
    Object.assign(dialog, DEFAULTS, opts, { open: true })
    return new Promise<boolean>((resolve) => {
      resolver = resolve
    })
  }

  return { dialog, ask, confirm: () => settle(true), cancel: () => settle(false) }
}
