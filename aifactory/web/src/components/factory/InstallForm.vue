<script setup lang="ts">
import { toRaw } from 'vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import type { FactoryOptions } from '@/lib/api'
const props = defineProps<{ options: FactoryOptions }>()
const emit = defineEmits<{ change: [options: FactoryOptions] }>()
const AZURE_LABELS = { organization: 'Azure organizace', project: 'Azure projekt', repository: 'Azure repozitář' } as const
const PROVIDERS = [{ value: 'local', label: 'Jen lokálně' }, { value: 'github', label: 'GitHub' }, { value: 'azure', label: 'Azure DevOps' }]
function edit(fn: (value: FactoryOptions) => void) {
  const value = structuredClone(toRaw(props.options))
  fn(value)
  emit('change', value)
}
function text(event: Event): string { return (event.target as HTMLInputElement).value }
</script>
<template>
  <fieldset>
    <legend>Instalace factory</legend>
    <label>Base <input :value="options.base" data-test="install-base" @input="edit(v => v.base = text($event))"></label>
    <label>Git hosting <SelectMenu :model-value="options.provider ?? ''" label="Git hosting" :options="PROVIDERS" data-test="install-provider" @update:model-value="edit(v => v.provider = $event)" /></label>
    <template v-if="options.provider === 'azure'">
      <label v-for="key in (['organization','project','repository'] as const)" :key="key">{{ AZURE_LABELS[key] }} <input :value="options.azure?.[key]" @input="edit(v => { if(v.azure) v.azure[key] = text($event) })"></label>
    </template>
    <label>Kořen dokumentů factory <input :value="options.docs_root" data-test="install-docs_root" @input="edit(v => v.docs_root = text($event))"></label>
    <p class="hint">Agenti, workflow, skilly a rozšíření se dědí z knihovny. Vlastní kopie v .factory/ má přednost.</p>
  </fieldset>
</template>
<style scoped>
label { display: inline-flex; align-items: center; gap: 8px; margin: 6px 12px 6px 0; }
input, select { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); padding: 6px; }
.hint { color: var(--dim); }
</style>
