<script setup lang="ts">
// Shared dropdown — replaces the native <select> across the dashboard.
// WAI-ARIA "select-only combobox": focus stays on the trigger button, the active
// option is announced through aria-activedescendant. The list is teleported to
// <body> with position: fixed, so it sits above the sticky topbar and is never
// clipped by a scroll container.
import { computed, nextTick, onBeforeUnmount, reactive, ref, useId, watch } from 'vue'
import { ChevronDown } from 'lucide-vue-next'
import { typeaheadIndex, typeaheadQuery, type SelectOption } from '@/lib/select'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    modelValue: string
    options: SelectOption[]
    label: string
    disabled?: boolean
    invalid?: boolean
    placeholder?: string
  }>(),
  { disabled: false, invalid: false, placeholder: '' },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const listId = `select-${useId()}`
const trigger = ref<HTMLButtonElement | null>(null)
const list = ref<HTMLElement | null>(null)
const open = ref(false)
const active = ref(-1)
const pos = reactive({ top: 0, left: 0, minWidth: 0, maxHeight: 320, measured: false })

const selectedIndex = computed(() => props.options.findIndex((o) => o.value === props.modelValue))
const current = computed(() => props.options[selectedIndex.value])

const GAP = 4
const EDGE = 8
const MAX_HEIGHT = 320
const PAGE = 10
const TYPEAHEAD_MS = 500

function optionId(i: number): string {
  return `${listId}-opt-${i}`
}

async function place() {
  pos.measured = false
  await nextTick()
  const t = trigger.value
  const l = list.value
  if (!t || !l || !open.value) return
  const r = t.getBoundingClientRect()
  const spaceBelow = window.innerHeight - r.bottom - GAP - EDGE
  const spaceAbove = r.top - GAP - EDGE
  const natural = Math.min(l.scrollHeight, MAX_HEIGHT)
  const below = natural <= spaceBelow || spaceBelow >= spaceAbove
  const maxHeight = Math.max(0, Math.min(MAX_HEIGHT, below ? spaceBelow : spaceAbove))
  const height = Math.min(natural, maxHeight)
  pos.maxHeight = maxHeight
  pos.top = below ? r.bottom + GAP : r.top - GAP - height
  pos.minWidth = r.width
  const width = Math.max(l.getBoundingClientRect().width, r.width)
  const maxLeft = Math.max(EDGE, window.innerWidth - width - EDGE)
  pos.left = Math.min(Math.max(r.left, EDGE), maxLeft)
  pos.measured = true
  revealActive()
}

function revealActive() {
  if (active.value < 0) return
  const el = document.getElementById(optionId(active.value))
  el?.scrollIntoView?.({ block: 'nearest' })
}

function onOutside(event: Event) {
  const target = event.target as Node | null
  if (target && (trigger.value?.contains(target) || list.value?.contains(target))) return
  close()
}

function onScroll(event: Event) {
  const target = event.target as Node | null
  if (target && list.value?.contains(target)) return
  close()
}

function onResize() {
  close()
}

function listen(on: boolean) {
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('mousedown', onOutside, true)
  window[method]('scroll', onScroll, true)
  window[method]('resize', onResize)
}

function openList() {
  if (props.disabled || open.value) return
  active.value = selectedIndex.value >= 0 ? selectedIndex.value : props.options.length ? 0 : -1
  open.value = true
  listen(true)
  void place()
}

function close() {
  if (!open.value) return
  open.value = false
  listen(false)
}

function toggle() {
  if (open.value) close()
  else openList()
}

function commit(i: number) {
  const opt = props.options[i]
  if (opt && opt.value !== props.modelValue) emit('update:modelValue', opt.value)
}

function choose(i: number) {
  commit(i)
  close()
  trigger.value?.focus()
}

function move(to: number) {
  const last = props.options.length - 1
  if (last < 0) return
  active.value = Math.min(Math.max(to, 0), last)
  void nextTick(revealActive)
}

// Typeahead: printable keys build a short buffer that resets after a pause.
let buffer = ''
let bufferTimer: ReturnType<typeof setTimeout> | undefined

function typeahead(key: string) {
  buffer += key
  clearTimeout(bufferTimer)
  bufferTimer = setTimeout(() => {
    buffer = ''
  }, TYPEAHEAD_MS)
  const query = typeaheadQuery(buffer)
  const from = open.value ? active.value : selectedIndex.value
  const start = query.length === 1 ? from : from - 1
  const labels = props.options.map((o) => o.label)
  const i = typeaheadIndex(labels, query, start)
  if (i < 0) return
  if (open.value) move(i)
  else commit(i)
}

function isPrintable(event: KeyboardEvent): boolean {
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey
}

function onKeydown(event: KeyboardEvent) {
  if (props.disabled) return
  const { key } = event
  if (!open.value) {
    if (key === 'ArrowDown' || key === 'ArrowUp' || key === 'Enter' || (key === ' ' && !buffer)) {
      event.preventDefault()
      openList()
    } else if (isPrintable(event)) {
      event.preventDefault()
      typeahead(key)
    }
    return
  }
  switch (key) {
    case 'ArrowDown':
      event.preventDefault()
      move(event.altKey ? active.value : active.value + 1)
      return
    case 'ArrowUp':
      event.preventDefault()
      if (event.altKey) choose(active.value)
      else move(active.value - 1)
      return
    case 'Home':
      event.preventDefault()
      move(0)
      return
    case 'End':
      event.preventDefault()
      move(props.options.length - 1)
      return
    case 'PageDown':
      event.preventDefault()
      move(active.value + PAGE)
      return
    case 'PageUp':
      event.preventDefault()
      move(active.value - PAGE)
      return
    case 'Enter':
      event.preventDefault()
      choose(active.value)
      return
    case ' ':
      event.preventDefault()
      if (buffer) typeahead(key)
      else choose(active.value)
      return
    case 'Escape':
      event.preventDefault()
      event.stopPropagation()
      close()
      return
    case 'Tab':
      commit(active.value)
      close()
      return
  }
  if (isPrintable(event)) {
    event.preventDefault()
    typeahead(key)
  }
}

watch(
  () => props.disabled,
  (now) => {
    if (now) close()
  },
)

watch(
  () => props.options.length,
  (n) => {
    if (active.value >= n) active.value = n - 1
    if (open.value) void place()
  },
)

onBeforeUnmount(() => {
  listen(false)
  clearTimeout(bufferTimer)
})
</script>

<template>
  <button
    ref="trigger"
    type="button"
    class="select-trigger"
    :class="{ open, invalid }"
    v-bind="$attrs"
    role="combobox"
    aria-haspopup="listbox"
    :aria-expanded="open ? 'true' : 'false'"
    :aria-controls="listId"
    :aria-activedescendant="open && active >= 0 ? optionId(active) : undefined"
    :aria-label="label"
    :aria-invalid="invalid ? 'true' : undefined"
    :disabled="disabled"
    :data-value="modelValue"
    @click="toggle"
    @keydown="onKeydown"
    @blur="close"
  >
    <span class="select-value" :class="{ faint: !current }">{{ current?.label ?? placeholder }}</span>
    <ChevronDown class="chevron" :size="16" aria-hidden="true" />
  </button>
  <Teleport to="body">
    <ul
      v-if="open"
      :id="listId"
      ref="list"
      role="listbox"
      class="select-list"
      data-test="select-list"
      :aria-label="label"
      :style="{
        top: `${pos.top}px`,
        left: `${pos.left}px`,
        minWidth: `${pos.minWidth}px`,
        maxHeight: `${pos.maxHeight}px`,
        visibility: pos.measured ? 'visible' : 'hidden',
      }"
      @mousedown.prevent
    >
      <li
        v-for="(opt, i) in options"
        :id="optionId(i)"
        :key="opt.value"
        role="option"
        :aria-selected="opt.value === modelValue ? 'true' : 'false'"
        :data-value="opt.value"
        :class="{ active: i === active, selected: opt.value === modelValue }"
        @mousemove="active = i"
        @click="choose(i)"
      >
        {{ opt.label }}
      </li>
    </ul>
  </Teleport>
</template>

<style scoped>
.select-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 120px;
  padding: 5px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.select-trigger:hover:not(:disabled),
.select-trigger:focus-visible,
.select-trigger.open {
  border-color: var(--blue);
}

.select-trigger:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 1px;
}

.select-trigger.invalid {
  border-color: var(--red);
}

.select-trigger:disabled {
  opacity: 0.5;
  cursor: default;
}

.select-value {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.select-value.faint {
  color: var(--faint);
}

.chevron {
  flex: none;
  color: var(--dim);
  transition: transform 0.12s ease-out;
}

.select-trigger.open .chevron {
  transform: rotate(180deg);
}

.select-list {
  position: fixed;
  z-index: var(--z-dropdown);
  box-sizing: border-box;
  margin: 0;
  padding: 4px;
  list-style: none;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-family: var(--sans);
  font-size: 16px;
  font-weight: 400;
  text-align: left;
  box-shadow: var(--shadow-pop);
  animation: select-in 0.1s ease-out;
}

.select-list li {
  padding: 6px 10px;
  border-radius: 6px;
  white-space: nowrap;
  cursor: pointer;
}

.select-list li.active {
  background: rgba(108, 182, 255, 0.14);
}

.select-list li.selected {
  color: var(--blue);
  font-weight: 600;
}

@keyframes select-in {
  from {
    opacity: 0;
  }
}
</style>
