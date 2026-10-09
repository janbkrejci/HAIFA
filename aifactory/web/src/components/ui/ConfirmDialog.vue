<script setup lang="ts">
// Shared modal confirmation dialog — replaces the browser confirm() across the dashboard.
// Esc and a click outside cancel, Enter confirms, Tab stays inside, and focus
// returns to the element that opened it.
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'

let seq = 0

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    message?: string
    confirmLabel?: string
    cancelLabel?: string
    tone?: 'default' | 'danger'
    confirmDisabled?: boolean
  }>(),
  { message: '', confirmLabel: 'Potvrdit', cancelLabel: 'Zrušit', tone: 'default' },
)

const emit = defineEmits<{ confirm: []; cancel: [] }>()

const uid = ++seq
const titleId = `confirm-title-${uid}`
const msgId = `confirm-msg-${uid}`
const panel = ref<HTMLElement | null>(null)
const okBtn = ref<HTMLButtonElement | null>(null)
let returnTo: HTMLElement | null = null

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

function focusables(): HTMLElement[] {
  return panel.value ? Array.from(panel.value.querySelectorAll<HTMLElement>(FOCUSABLE)) : []
}

function focusInitial() {
  if (okBtn.value && !okBtn.value.disabled) okBtn.value.focus()
  else focusables()[0]?.focus()
}

function onFocusIn(e: FocusEvent) {
  const target = e.target as Node | null
  if (panel.value && target && !panel.value.contains(target)) focusInitial()
}

function restoreFocus() {
  const el = returnTo
  returnTo = null
  document.removeEventListener('focusin', onFocusIn)
  void nextTick(() => {
    if (el && el.isConnected) el.focus()
  })
}

watch(
  () => props.open,
  async (open, was) => {
    if (open) {
      returnTo = document.activeElement instanceof HTMLElement ? document.activeElement : null
      document.addEventListener('focusin', onFocusIn)
      await nextTick()
      focusInitial()
    } else if (was) {
      restoreFocus()
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (props.open) restoreFocus()
})

function onKeydown(e: KeyboardEvent) {
  // Nested controls such as SelectMenu own keys they have already handled.
  if (e.defaultPrevented) return
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('cancel')
  } else if (e.key === 'Enter') {
    if (props.confirmDisabled) return
    const target = e.target as HTMLElement | null
    if (target?.dataset?.test === 'confirm-cancel') return // Enter activates Zrušit natively
    e.preventDefault()
    emit('confirm')
  } else if (e.key === 'Tab') {
    const items = focusables()
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement as HTMLElement | null
    const inside = !!active && !!panel.value?.contains(active)
    if (!inside) {
      e.preventDefault()
      first.focus()
    } else if (e.shiftKey && active === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      e.preventDefault()
      first.focus()
    }
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" data-test="confirm-backdrop" @mousedown.self="emit('cancel')">
      <div
        ref="panel"
        class="modal"
        role="dialog"
        aria-modal="true"
        :aria-labelledby="titleId"
        :aria-describedby="message ? msgId : undefined"
        data-test="confirm-dialog"
        @keydown="onKeydown"
      >
        <h2 :id="titleId" class="modal-title">{{ title }}</h2>
        <p v-if="message" :id="msgId" class="modal-message" data-test="confirm-message">{{ message }}</p>
        <slot />
        <div class="modal-actions">
          <button type="button" class="btn" data-test="confirm-cancel" @click="emit('cancel')">
            {{ cancelLabel }}
          </button>
          <button
            ref="okBtn"
            :disabled="confirmDisabled"
            type="button"
            class="btn ok"
            :class="tone"
            data-test="confirm-ok"
            @click="emit('confirm')"
          >
            {{ confirmLabel }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(3, 6, 12, 0.6);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  animation: fade-in 0.12s ease-out;
}

:global([data-theme='light']) .modal-backdrop {
  background: rgba(20, 30, 50, 0.35);
}

.modal {
  width: 100%;
  max-width: min(560px, calc(100vw - 32px));
  padding: 20px 22px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  background-color: var(--panel);
  color: var(--text);
  box-shadow: var(--shadow-pop);
  max-height: 85vh;
  overflow: auto;
}

.btn:disabled { opacity: .5; cursor: default; }

.modal-title {
  margin: 0 0 10px;
  font-size: 19px;
  font-weight: 700;
  overflow-wrap: anywhere;
}

.modal-message {
  margin: 0 0 16px;
  color: var(--dim);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}

.btn {
  padding: 9px 16px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.btn:focus-visible {
  outline: 2px solid var(--cyan);
  outline-offset: 2px;
}

.btn.ok {
  border-color: var(--green);
  background: var(--green);
  color: #082413;
  font-weight: 700;
}

.btn.ok.danger {
  border-color: rgba(255, 111, 103, 0.55);
  background: var(--red);
  color: #30100d;
}

@keyframes fade-in {
  from {
    opacity: 0;
  }
}
</style>
