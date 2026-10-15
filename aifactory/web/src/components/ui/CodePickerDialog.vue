<script setup lang="ts">
// Modal picker of one backlog code with a search over the code and the title. The caller passes
// only the codes that can be chosen (already chosen ones and the task itself are left out).
// A click picks a code at once; arrows, Home and End move the selection, Enter picks it, Esc
// closes without a choice. The list carries the hooks of SelectMenu's list (`select-list`,
// `data-value`), so the browser tests drive both pickers the same way.
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Search } from 'lucide-vue-next'
import type { SelectOption } from '@/lib/select'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps<{ open: boolean; heading: string; options: SelectOption[] }>()
const emit = defineEmits<{ choose: [code: string]; close: [] }>()
const query = ref('')
const selected = ref('')
const search = ref<HTMLInputElement | null>(null)

function fold(text: string): string {
  return text.toLocaleLowerCase('cs')
}
/** The title part of an option label `CODE · Title`, empty when the label is just the code. */
function titleOf(option: SelectOption): string {
  const prefix = `${option.value} · `
  return option.label.startsWith(prefix) ? option.label.slice(prefix.length) : option.label === option.value ? '' : option.label
}
const filtered = computed(() => {
  const q = fold(query.value.trim())
  return props.options.filter((o) => fold(o.value).includes(q) || fold(o.label).includes(q))
})
const values = computed(() => filtered.value.map((o) => o.value))
watch(() => props.open, async (open) => {
  if (!open) return
  query.value = ''; selected.value = ''
  await nextTick(); await nextTick()
  search.value?.focus()
}, { immediate: true })
// Typing keeps the first match selected, so Enter in the search field picks it.
watch(values, (list) => { if (!list.includes(selected.value)) selected.value = list[0] ?? '' }, { immediate: true })
function choose() { if (values.value.includes(selected.value)) emit('choose', selected.value) }
function navigate(event: KeyboardEvent) {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
  const list = values.value
  if (!keys.includes(event.key) || !list.length) return
  event.preventDefault()
  const index = list.indexOf(selected.value)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? list.length - 1 : index < 0 ? (event.key === 'ArrowDown' ? 0 : list.length - 1) : (index + (event.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length
  selected.value = list[next]!
  void nextTick(() => document.querySelector<HTMLButtonElement>('[data-test="select-list"] [aria-selected="true"]')?.focus())
}
function fromSearch(event: KeyboardEvent) {
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') navigate(event)
}
</script>

<template>
  <ConfirmDialog :open="open" :title="heading" confirm-label="Přidat" :confirm-disabled="!values.includes(selected)" @cancel="emit('close')" @confirm="choose">
    <label class="code-search"><Search :size="18" aria-hidden="true" /><input ref="search" v-model="query" data-test="code-picker-search" type="search" aria-label="Hledat podle kódu nebo názvu" placeholder="Hledat podle kódu nebo názvu…" @keydown="fromSearch" @keydown.enter.prevent.stop="choose"></label>
    <p class="code-count">{{ filtered.length }} z {{ options.length }}</p>
    <div class="code-list" role="listbox" :aria-label="heading" data-test="select-list" @keydown="navigate">
      <button v-for="option in filtered" :key="option.value" type="button" role="option" :aria-selected="selected === option.value" :tabindex="selected === option.value ? 0 : -1" :data-value="option.value" @click="selected = option.value; choose()">
        <span class="code">{{ option.value }}</span>
        <span class="name">{{ titleOf(option) }}</span>
        <Check v-if="selected === option.value" :size="16" aria-hidden="true" />
      </button>
      <p v-if="!filtered.length" class="no-codes">{{ options.length ? 'Nic neodpovídá hledání.' : 'Není co přidat.' }}</p>
    </div>
  </ConfirmDialog>
</template>

<style scoped>
.code-search { display: flex; align-items: center; gap: 10px; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; color: var(--dim); background: var(--panel-2); }
.code-search:focus-within { border-color: var(--cyan); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cyan) 12%, transparent); }
.code-search input { width: 100%; border: 0; outline: 0; padding: 0; background: transparent; color: var(--text); font: inherit; }
.code-count { color: var(--faint); font-size: 12px; margin: 10px 0; }
.code-list { display: flex; flex-direction: column; gap: 4px; max-height: 45vh; overflow-y: auto; }
.code-list button { display: flex; align-items: center; gap: 12px; flex: none; width: 100%; min-width: 0; padding: 9px 12px; border: 1px solid transparent; border-radius: 8px; text-align: left; background: transparent; color: var(--dim); font: inherit; cursor: pointer; }
.code-list button[aria-selected="true"] { border-color: color-mix(in srgb, var(--cyan) 40%, transparent); background: color-mix(in srgb, var(--cyan) 10%, var(--panel)); color: var(--text); }
.code-list button:hover { background: var(--panel-2); }
.code { flex: none; font-family: var(--mono); font-size: 13px; }
.name { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.no-codes { color: var(--faint); padding: 18px 12px; text-align: center; }
</style>
