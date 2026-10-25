<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { errorText } from '../../lib/format'
import { execTerminal, fetchTerminal } from '../../lib/terminal'

const emit = defineEmits<{ close: [] }>()
const enabled = ref(false)
const loading = ref(true)
const cwd = ref('')
const command = ref('')
const running = ref(false)
const error = ref('')
const output = ref<{ text: string; kind: string }[]>([])
const input = ref<HTMLInputElement>()
const viewport = ref<HTMLElement>()
const history: string[] = []
let historyIndex = 0
let draft = ''
let active: AbortController | undefined
const infoController = new AbortController()
const previousFocus = document.activeElement as HTMLElement | null
let disposed = false

async function append(text: string, kind: string) {
  output.value.push({ text, kind })
  await nextTick()
  if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight
}
async function run() {
  if (running.value || !enabled.value || !command.value.trim()) return
  const text = command.value
  command.value = ''
  history.push(text)
  historyIndex = history.length
  draft = ''
  void append(`${cwd.value} $ ${text}\n`, 'command')
  running.value = true
  const controller = new AbortController()
  active = controller
  try {
    await execTerminal(text, cwd.value, controller.signal, event => {
      if (disposed) return
      if (event.type === 'out') void append(event.text, event.stream)
      else {
        cwd.value = event.cwd
        if (event.code !== 0) void append(`\nNávratový kód: ${event.code}\n`, 'stderr')
      }
    })
  } catch (err) {
    if (!disposed) void append(controller.signal.aborted ? '^C\n' : `${errorText(err)}\n`, 'stderr')
  } finally {
    active = undefined
    running.value = false
    if (!disposed) { await nextTick(); input.value?.focus() }
  }
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    event.preventDefault()
    event.stopPropagation()
    emit('close')
  } else if (event.ctrlKey && event.key.toLowerCase() === 'c' && running.value) {
    event.preventDefault()
    active?.abort()
  } else if (event.target === input.value && ['ArrowUp', 'ArrowDown'].includes(event.key)) {
    event.preventDefault()
    if (historyIndex === history.length) draft = command.value
    historyIndex = Math.max(0, Math.min(history.length, historyIndex + (event.key === 'ArrowUp' ? -1 : 1)))
    command.value = history[historyIndex] ?? draft
  } else if (event.key === 'Tab') {
    // Keep keyboard focus inside this modal, including while the input is unavailable.
    const controls = [document.getElementById('terminal-close'), input.value].filter(Boolean) as HTMLElement[]
    const index = controls.indexOf(document.activeElement as HTMLElement)
    event.preventDefault()
    controls[(index + (event.shiftKey ? controls.length - 1 : 1)) % controls.length]?.focus()
  }
}
onMounted(async () => {
  document.getElementById('terminal-close')?.focus()
  try {
    const info = await fetchTerminal(infoController.signal)
    if (disposed) return
    enabled.value = info.enabled
    cwd.value = info.cwd
  } catch (err) {
    if (!disposed) error.value = errorText(err)
  } finally {
    loading.value = false
    if (!disposed) { await nextTick(); input.value?.focus() }
  }
})
onBeforeUnmount(() => {
  disposed = true
  infoController.abort()
  active?.abort()
  previousFocus?.focus()
})
</script>

<template>
  <section class="terminal-overlay" role="dialog" aria-modal="true" aria-label="Terminál" data-test="terminal-overlay" @keydown="keydown">
    <header><span>Terminál</span><button id="terminal-close" type="button" aria-label="Zavřít terminál" @click="emit('close')">×</button></header>
    <div ref="viewport" class="terminal-output" role="log" aria-label="Výstup terminálu"><span v-for="(entry, i) in output" :key="i" :class="entry.kind">{{ entry.text }}</span></div>
    <p v-if="loading">Načítám terminál…</p>
    <p v-else-if="error" role="alert">{{ error }}</p>
    <p v-else-if="!enabled" data-test="terminal-disabled">Terminál je dostupný jen při dashboardu na tomto počítači (loopback).</p>
    <form v-else @submit.prevent="run">
      <label for="terminal-command">{{ cwd }} $</label>
      <input id="terminal-command" ref="input" v-model="command" aria-label="Příkaz" autocomplete="off" spellcheck="false" :readonly="running" />
      <span v-if="running" class="running">Běží… Ctrl+C zruší</span>
    </form>
  </section>
</template>

<style scoped>
.terminal-overlay { position: fixed; inset: 0; z-index: 1000; display: flex; flex-direction: column; padding: 20px; background: #0b0f18; color: #e7eaf3; font: 14px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #303849; padding-bottom: 12px; }
button { background: transparent; color: inherit; border: 1px solid #303849; border-radius: 6px; font: inherit; font-size: 24px; cursor: pointer; width: 36px; }
.terminal-output { flex: 1; min-height: 0; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 12px 0; }
.stderr, [role="alert"] { color: #ff8e96; }
.command { color: #5ad2dd; }
form { display: flex; align-items: baseline; flex-wrap: wrap; gap: 8px; border-top: 1px solid #303849; padding-top: 12px; }
label { overflow-wrap: anywhere; }
input { flex: 1; min-width: 100px; background: transparent; color: inherit; border: 0; outline: none; font: inherit; }
.running { color: #b3bbcc; }
</style>
