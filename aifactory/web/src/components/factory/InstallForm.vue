<script setup lang="ts">
import { computed, toRaw } from 'vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import type { FactoryOptions, FactoryInitPlan } from '@/lib/api'
import { MODEL_SUGGESTIONS, THINKING_LEVELS } from '@/lib/roster'
const props = defineProps<{ options: FactoryOptions; plan: FactoryInitPlan }>()
const emit = defineEmits<{ change: [options: FactoryOptions] }>()
const DIR_LABELS = { backlog_dir: 'Adresář backlogu', specs_dir: 'Adresář specifikací', docs_dir: 'Adresář dokumentace' } as const
const AZURE_LABELS = { organization: 'Azure organizace', project: 'Azure projekt', repository: 'Azure repozitář' } as const
const PROVIDERS = [{ value: 'local', label: 'Jen lokálně' }, { value: 'github', label: 'GitHub' }, { value: 'azure', label: 'Azure DevOps' }]
/** The installer's own default, used when the field stays empty. */
const defaultTest = computed(() => typeof props.plan.test_command === 'object' && props.plan.test_command?.source === 'default' ? props.plan.test_command.command : '')
const harnessOptions = computed(() => Object.keys(props.plan.detected?.harnesses ?? {}).map(name => ({ value: name, label: name })))
function edit(fn: (value: FactoryOptions) => void) {
  const value = structuredClone(toRaw(props.options))
  fn(value)
  emit('change', value)
}
function text(event: Event): string { return (event.target as HTMLInputElement).value }
function toggle(key: 'agents' | 'workflows', name: string) {
  edit(v => { v[key] = v[key]?.includes(name) ? v[key]!.filter(n => n !== name) : [...(v[key] ?? []), name] })
}
function binding(name: string, key: 'harness' | 'model' | 'thinking', value: string) {
  edit(v => { const entry = v.bind?.[name]; if (!entry) return; if (key === 'harness') entry.harness = value; else entry[key] = value || null })
}
</script>
<template>
  <fieldset>
    <legend>Instalace factory</legend>
    <label>Base <input :value="options.base" data-test="install-base" @input="edit(v => v.base = text($event))"></label>
    <label>Git hosting <SelectMenu :model-value="options.provider ?? ''" label="Git hosting" :options="PROVIDERS" data-test="install-provider" @update:model-value="edit(v => v.provider = $event)" /></label>
    <template v-if="options.provider === 'azure'">
      <label v-for="key in (['organization','project','repository'] as const)" :key="key">{{ AZURE_LABELS[key] }} <input :value="options.azure?.[key]" @input="edit(v => { if(v.azure) v.azure[key] = text($event) })"></label>
    </template>
    <label v-for="key in (['backlog_dir','specs_dir','docs_dir'] as const)" :key="key">{{ DIR_LABELS[key] }} <input :value="options[key]" :data-test="`install-${key}`" @input="edit(v => v[key] = text($event))"></label>
    <label>Testovací příkaz <input :value="options.test_command ?? ''" :placeholder="defaultTest ? `Prázdné = ${defaultTest}` : 'Prázdné = výchozí instalátoru'" data-test="install-test_command" @input="edit(v => v.test_command = text($event))"></label>
    <h3>Agenti</h3>
    <datalist id="install-models"><option v-for="m in MODEL_SUGGESTIONS" :key="m" :value="m" /></datalist>
    <datalist id="install-thinking"><option v-for="t in THINKING_LEVELS" :key="t" :value="t" /></datalist>
    <div v-for="agent in plan.available?.agents" :key="agent.name">
      <label><input type="checkbox" :checked="options.agents?.includes(agent.name)" @change="toggle('agents', agent.name)">{{ agent.name }} — {{ agent.purpose }}</label>
      <div v-if="options.agents?.includes(agent.name) && options.bind?.[agent.name]" class="binding" :data-agent="agent.name">
        <label>Harness <SelectMenu :model-value="options.bind[agent.name]!.harness" label="Harness" :options="harnessOptions" :data-test="`harness-${agent.name}`" @update:model-value="binding(agent.name, 'harness', $event)" /></label>
        <label>Model <input :value="options.bind[agent.name]!.model" list="install-models" placeholder="Podle harnessu" :data-test="`model-${agent.name}`" @input="binding(agent.name, 'model', text($event))"></label>
        <label>Přemýšlení <input :value="options.bind[agent.name]!.thinking" list="install-thinking" placeholder="Podle harnessu" :data-test="`thinking-${agent.name}`" @input="binding(agent.name, 'thinking', text($event))"></label>
        <p v-if="!plan.detected?.harnesses[options.bind[agent.name]!.harness]?.installed" class="warning">CLI pro {{ options.bind[agent.name]!.harness }} není nainstalované.</p>
      </div>
    </div>
    <p v-if="plan.added_agents?.length">Workflow přidává agenty: {{ plan.added_agents.join(', ') }}</p>
    <h3>Workflow</h3>
    <label v-for="w in plan.available?.workflows" :key="w.name"><input type="checkbox" :checked="options.workflows?.includes(w.name)" @change="toggle('workflows',w.name)">{{ w.name }}</label>
  </fieldset>
</template>
<style scoped>
label { display: inline-flex; align-items: center; gap: 8px; margin: 6px 12px 6px 0; }
input, select { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); padding: 6px; }
.binding { padding-left: 24px; }
.warning { color: var(--amber); }
</style>
