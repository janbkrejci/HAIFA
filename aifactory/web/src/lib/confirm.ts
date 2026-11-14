// Promise API over the shared ConfirmDialog: `await ask({...})` resolves true on
// confirm and false on cancel. Bind `dialog` to <ConfirmDialog v-bind="dialog" …>.
import { computed, reactive, shallowRef } from 'vue'
import { t } from './i18n'

export type ConfirmTone = 'default' | 'danger'

export interface ConfirmOptions {
  title: string
  message?: string
  confirmLabel?: string
  cancelLabel?: string
  tone?: ConfirmTone
  /** Potvrdit stays disabled (e.g. while something blocks the action). */
  confirmDisabled?: boolean
}

const defaults = () => ({ message: '', confirmLabel: t('common.confirm'), cancelLabel: t('common.cancel'), tone: 'default' as ConfirmTone, confirmDisabled: false })

export function useConfirm() {
  const open = shallowRef(false)
  const options = shallowRef<ConfirmOptions | (() => ConfirmOptions)>({ title: '' })
  const resolved = computed(() => ({ ...defaults(), ...(typeof options.value === 'function' ? options.value() : options.value) }))
  const dialog = reactive({
    get open() { return open.value },
    get title() { return resolved.value.title },
    get message() { return resolved.value.message },
    get confirmLabel() { return resolved.value.confirmLabel },
    get cancelLabel() { return resolved.value.cancelLabel },
    get tone() { return resolved.value.tone },
    get confirmDisabled() { return resolved.value.confirmDisabled },
  })
  let resolver: ((ok: boolean) => void) | null = null

  function settle(ok: boolean) {
    open.value = false
    const resolve = resolver
    resolver = null
    resolve?.(ok)
  }

  function ask(opts: ConfirmOptions | (() => ConfirmOptions)): Promise<boolean> {
    settle(false) // an earlier question still open counts as cancelled
    options.value = opts
    open.value = true
    return new Promise<boolean>((resolve) => {
      resolver = resolve
    })
  }

  return { dialog, ask, confirm: () => settle(true), cancel: () => settle(false) }
}
