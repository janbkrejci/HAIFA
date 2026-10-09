<script setup lang="ts">
// The folder path of the Add repository page, with suggestions of the subfolders of the typed
// folder (GET /api/fs/dirs, tagged git and factory). ↑↓ pick a suggestion, Enter or a click
// takes it, Esc and blur close the list; Enter without a picked suggestion submits.
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchDirs, type FsEntry } from '@/lib/api'
import { expandHome, filterEntries, splitForSuggest } from '@/lib/addRepo'

const props = withDefaults(defineProps<{ modelValue: string; home: string | null; debounce?: number }>(), {
  debounce: 150,
})
const emit = defineEmits<{ 'update:modelValue': [value: string]; submit: [] }>()

const input = ref<HTMLInputElement | null>(null)
const suggestions = ref<FsEntry[]>([])
const open = ref(false)
const active = ref(-1)
/** The folder part of the value the suggestions belong to, as typed (e.g. `~/`). */
let shownDir = ''
const cache = new Map<string, FsEntry[]>()
let generation = 0
let timer: ReturnType<typeof setTimeout> | null = null

function hide() {
  open.value = false
  active.value = -1
}

async function suggest(value: string): Promise<void> {
  const mine = ++generation
  const split = splitForSuggest(value)
  if (split === null || props.home === null) return hide()
  const dir = expandHome(split.dir, props.home)
  if (!dir.startsWith('/')) return hide()
  let entries = cache.get(dir)
  if (entries === undefined) {
    try {
      entries = (await fetchDirs(dir)).entries
    } catch {
      if (mine === generation) hide()
      return
    }
    cache.set(dir, entries)
  }
  if (mine !== generation) return
  suggestions.value = filterEntries(entries, split.prefix)
  shownDir = split.dir
  active.value = -1
  open.value = suggestions.value.length > 0
}

function schedule(value: string) {
  if (timer !== null) clearTimeout(timer)
  timer = setTimeout(() => {
    timer = null
    void suggest(value)
  }, props.debounce)
}

function onInput(event: Event) {
  const value = (event.target as HTMLInputElement).value
  emit('update:modelValue', value)
  schedule(value)
}

function choose(entry: FsEntry) {
  const value = `${shownDir}${entry.name}/`
  emit('update:modelValue', value)
  hide()
  void suggest(value)
  void nextTick(() => input.value?.focus())
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' && open.value) {
    event.preventDefault()
    active.value = (active.value + 1) % suggestions.value.length
  } else if (event.key === 'ArrowUp' && open.value) {
    event.preventDefault()
    active.value = active.value <= 0 ? suggestions.value.length - 1 : active.value - 1
  } else if (event.key === 'Enter') {
    event.preventDefault()
    const entry = open.value ? suggestions.value[active.value] : undefined
    if (entry) {
      choose(entry)
    } else {
      generation++
      hide()
      emit('submit')
    }
  } else if (event.key === 'Escape') {
    generation++
    if (timer !== null) clearTimeout(timer)
    hide()
  }
}

function onBlur() {
  generation++
  if (timer !== null) clearTimeout(timer)
  hide()
}

onMounted(() => input.value?.focus())
onBeforeUnmount(() => {
  if (timer !== null) clearTimeout(timer)
})
</script>

<template>
  <div class="path-field">
    <input
      ref="input"
      class="path-input mono"
      type="text"
      spellcheck="false"
      autocomplete="off"
      aria-label="Cesta ke složce repozitáře"
      role="combobox"
      :aria-expanded="open ? 'true' : 'false'"
      aria-autocomplete="list"
      :value="modelValue"
      data-test="add-path"
      @input="onInput"
      @keydown="onKeydown"
      @blur="onBlur"
    />
    <ul v-if="open" class="suggestions" role="listbox" data-test="path-suggestions">
      <li
        v-for="(entry, i) in suggestions"
        :key="entry.path"
        class="suggestion"
        :class="{ active: i === active }"
        role="option"
        :aria-selected="i === active ? 'true' : 'false'"
        data-test="path-suggestion"
        @mousedown.prevent="choose(entry)"
      >
        <span class="name mono">{{ entry.name }}/</span>
        <span v-if="entry.is_git" class="tag git" data-test="tag-git">git</span>
        <span v-if="entry.has_factory" class="tag factory" data-test="tag-factory">factory</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.path-field {
  position: relative;
  flex: 1;
  min-width: 0;
}

.path-input {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 15px;
}

.path-input:focus {
  outline: 2px solid var(--cyan);
  outline-offset: 1px;
}

.suggestions {
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 4px);
  z-index: var(--z-dropdown);
  max-height: 320px;
  overflow-y: auto;
  margin: 0;
  padding: 4px;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow-pop);
}

.suggestion {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  cursor: pointer;
}

.suggestion.active,
.suggestion:hover {
  background: rgba(108, 182, 255, 0.14);
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag {
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
}

.tag.git {
  color: var(--blue);
}

.tag.factory {
  color: var(--purple);
}
</style>
