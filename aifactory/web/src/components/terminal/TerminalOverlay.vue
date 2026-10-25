<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Terminal } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { errorText } from '../../lib/format'
import { createTerminalSession, deleteTerminalSession, fetchTerminal, inputTerminal, resizeTerminal, streamTerminal } from '../../lib/terminal'

const emit = defineEmits<{ close: [] }>()
const enabled = ref(false)
const pty = ref(false)
const loading = ref(true)
const starting = ref(false)
const ended = ref(false)
const error = ref('')
const viewport = ref<HTMLElement>()
const infoController = new AbortController()
const previousFocus = document.activeElement as HTMLElement | null
let disposed = false
let cwd = ''
let term: Terminal | undefined
let fit: FitAddon | undefined
let observer: ResizeObserver | undefined
let subscription: { dispose(): void } | undefined
let session: { id: string; controller: AbortController; queue: Promise<void> } | undefined

function removeSession() {
  const current = session
  session = undefined
  current?.controller.abort()
  if (current) void deleteTerminalSession(current.id).catch(() => {})
}
function enqueue(operation: (id: string, signal: AbortSignal) => Promise<void>) {
  const current = session
  if (!current) return
  // Preserve keystroke and resize order even over a slow connection.
  current.queue = current.queue.then(async () => {
    if (!current.controller.signal.aborted) await operation(current.id, current.controller.signal)
  }).catch(err => {
    if (!disposed && session === current) error.value = errorText(err)
  })
}
function resize() {
  if (!term || !fit || disposed) return
  fit.fit()
  const size = { cols: term.cols, rows: term.rows }
  enqueue((id, signal) => resizeTerminal(id, size, signal))
}
async function start() {
  if (disposed || starting.value || session || !term) return
  starting.value = true
  ended.value = false
  error.value = ''
  term.reset()
  fit?.fit()
  try {
    const { id } = await createTerminalSession({ cols: term.cols, rows: term.rows }, cwd)
    if (disposed) {
      await deleteTerminalSession(id).catch(() => {})
      return
    }
    const current = { id, controller: new AbortController(), queue: Promise.resolve() }
    session = current
    // A resize may have happened while creation was in flight.
    resize()
    term.focus()
    void streamTerminal(id, current.controller.signal, bytes => {
      if (!disposed && session === current) term?.write(bytes)
    }).catch(err => {
      if (!disposed && session === current) error.value = errorText(err)
    }).finally(() => {
      if (!disposed && session === current) {
        removeSession()
        ended.value = true
      }
    })
  } catch (err) {
    if (!disposed) { error.value = errorText(err); ended.value = true }
  } finally {
    starting.value = false
  }
}
function dispose() {
  if (disposed) return
  disposed = true
  infoController.abort()
  observer?.disconnect()
  subscription?.dispose()
  removeSession()
  term?.dispose()
}
function close() {
  dispose()
  emit('close')
}
onMounted(async () => {
  window.addEventListener('pagehide', dispose)
  document.getElementById('terminal-close')?.focus()
  try {
    const info = await fetchTerminal(infoController.signal)
    if (disposed) return
    enabled.value = info.enabled
    pty.value = info.pty
    cwd = info.cwd
    loading.value = false
    if (!info.enabled || !info.pty) return
    await nextTick()
    if (disposed) return
    term = new Terminal({
      cursorBlink: true, fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace', fontSize: 14,
      theme: { background: '#0b0f18', foreground: '#e7eaf3', cursor: '#5ad2dd', selectionBackground: '#303849' },
    })
    fit = new FitAddon()
    term.loadAddon(fit)
    term.open(viewport.value!)
    subscription = term.onData(data => {
      if (ended.value && data === '\r') void start()
      else enqueue((id, signal) => inputTerminal(id, data, signal))
    })
    observer = new ResizeObserver(resize)
    observer.observe(viewport.value!)
    await start()
  } catch (err) {
    if (!disposed) error.value = errorText(err)
  } finally {
    loading.value = false
  }
})
onBeforeUnmount(() => {
  dispose()
  window.removeEventListener('pagehide', dispose)
  previousFocus?.focus()
})
</script>

<template>
  <section class="terminal-overlay" role="dialog" aria-modal="true" aria-label="Terminál" data-test="terminal-overlay">
    <header><span>Terminál</span><button id="terminal-close" type="button" aria-label="Zavřít terminál" @click="close">×</button></header>
    <p v-if="loading || starting">Načítám terminál…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-if="!loading && !enabled" data-test="terminal-disabled">Terminál je dostupný jen při dashboardu na tomto počítači (loopback).</p>
    <p v-else-if="!loading && !pty" data-test="terminal-unsupported">Interaktivní terminál na tomto stroji není dostupný.</p>
    <div v-show="enabled && pty" ref="viewport" class="terminal-viewport" />
    <p v-if="ended" role="status">Sezení terminálu skončilo. <button type="button" class="restart" @click="start">Nové sezení (Enter)</button></p>
  </section>
</template>

<style scoped>
.terminal-overlay { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; padding: 12px; background: #0b0f18; color: #e7eaf3; font: 14px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #303849; padding-bottom: 8px; margin-bottom: 8px; }
button { background: transparent; color: inherit; border: 1px solid #303849; border-radius: 6px; font: inherit; font-size: 24px; cursor: pointer; width: 36px; }
.terminal-viewport { flex: 1; min-height: 0; overflow: hidden; }
[role="alert"] { color: #ff8e96; }
.restart { font-size: inherit; width: auto; padding: 4px 8px; }
</style>
