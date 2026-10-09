<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Check, Search } from 'lucide-vue-next'
import ConfirmDialog from './ConfirmDialog.vue'

const props = defineProps<{ open: boolean; harness: string; models: string[]; model: string }>()
const emit = defineEmits<{ choose: [model: string]; close: [] }>()
const query = ref('')
const selected = ref('')
const search = ref<HTMLInputElement | null>(null)
const filtered = computed(() => props.models.filter(m => m.toLowerCase().includes(query.value.trim().toLowerCase())))
watch(() => props.open, async open => {
  if (!open) return
  query.value = ''; selected.value = props.model
  await nextTick(); await nextTick()
  search.value?.focus()
}, { immediate: true })
function choose() { if (filtered.value.includes(selected.value)) emit('choose', selected.value) }
function navigate(event: KeyboardEvent) {
  const keys = ['ArrowDown', 'ArrowUp', 'Home', 'End']
  if (!keys.includes(event.key) || !filtered.value.length) return
  event.preventDefault()
  const index = filtered.value.indexOf(selected.value)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? filtered.value.length - 1 : index < 0 ? (event.key === 'ArrowDown' ? 0 : filtered.value.length - 1) : (index + (event.key === 'ArrowDown' ? 1 : -1) + filtered.value.length) % filtered.value.length
  selected.value = filtered.value[next]!
  void nextTick(() => document.querySelector<HTMLButtonElement>('[data-test="model-picker-list"] [aria-selected="true"]')?.focus())
}
</script>

<template>
  <ConfirmDialog :open="open" :title="`Model pro ${harness}`" confirm-label="Vybrat model" :confirm-disabled="!filtered.includes(selected)" @cancel="emit('close')" @confirm="choose">
    <label class="model-search"><Search :size="18" aria-hidden="true" /><input ref="search" v-model="query" data-test="model-picker-search" type="search" aria-label="Filtrovat modely" placeholder="Filtrovat modely…" @keydown.enter.prevent.stop="choose"></label>
    <p class="model-count">{{ filtered.length }} z {{ models.length }} modelů</p>
    <div class="model-list" role="listbox" aria-label="Dostupné modely" data-test="model-picker-list" @keydown="navigate">
      <button v-for="modelName in filtered" :key="modelName" type="button" role="option" :aria-selected="selected === modelName" :tabindex="selected === modelName || (!filtered.includes(selected) && modelName === filtered[0]) ? 0 : -1" :data-model="modelName" @click="selected = modelName" @dblclick="selected = modelName; choose()">
        <span>{{ modelName }}</span><Check v-if="selected === modelName" :size="16" aria-hidden="true" />
      </button>
      <p v-if="!filtered.length" class="no-models">Žádný model neodpovídá filtru.</p>
    </div>
  </ConfirmDialog>
</template>

<style scoped>
.model-search { display: flex; align-items: center; gap: 10px; border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px; color: var(--dim); background: var(--panel-2); }
.model-search:focus-within { border-color: var(--cyan); box-shadow: 0 0 0 3px color-mix(in srgb, var(--cyan) 12%, transparent); }
.model-search input { width: 100%; border: 0; outline: 0; padding: 0; background: transparent; color: var(--text); font: inherit; }
.model-count { color: var(--faint); font-size: 12px; margin: 10px 0; }
.model-list { display: flex; flex-direction: column; gap: 4px; max-height: 45vh; overflow-y: auto; }
.model-list button { display: flex; justify-content: space-between; align-items: center; gap: 12px; flex: none; width: 100%; padding: 11px 12px; border: 1px solid transparent; border-radius: 8px; text-align: left; background: transparent; color: var(--dim); font: inherit; cursor: pointer; }
.model-list button[aria-selected="true"] { border-color: color-mix(in srgb, var(--cyan) 40%, transparent); background: color-mix(in srgb, var(--cyan) 10%, var(--panel)); color: var(--text); }
.model-list button:hover { background: var(--panel-2); }
.no-models { color: var(--faint); padding: 18px 12px; text-align: center; }
</style>
