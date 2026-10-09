<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { fetchHarnessSettings, saveHarnessSettings, testHarness, type HarnessCatalog, type HarnessSettings } from '@/lib/machineHarnesses'
import { errorText } from '@/lib/format'
import ConfirmDialog from './ui/ConfirmDialog.vue'
import ModelPickerDialog from './ui/ModelPickerDialog.vue'
import { ChevronRight, Play } from 'lucide-vue-next'
import Spinner from './ui/Spinner.vue'
import SelectMenu from './ui/SelectMenu.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: []; saved: []; tested: [] }>()
const catalog = ref<HarnessCatalog | null>(null)
const settings = ref<HarnessSettings | null>(null)
const loading = ref(false)
const saving = ref(false)
const testing = ref<string | null>(null)
const modelPicker = ref<string | null>(null)
const error = ref('')
function thinkingOptions(name: string) {
  const model = settings.value?.harnesses[name]?.model ?? ''
  return (catalog.value?.thinking_levels?.[name]?.[model] ?? []).map(value => ({ value, label: value === 'off' ? 'Vypnuto' : value }))
}
function defaultThinking(name: string, model: string) { return catalog.value?.thinking_defaults?.[name]?.[model] ?? null }
let generation = 0
function testResult(name: string) { return catalog.value?.tests?.[name]?.[settings.value?.harnesses[name]?.model ?? ''] }
function eligible(name: string) { return !!settings.value?.harnesses[name]?.enabled && !!settings.value?.harnesses[name]?.model && !!catalog.value?.available[name] && testResult(name)?.ok !== false }
const canSave = computed(() => !!settings.value && !loading.value && !saving.value && !testing.value && (settings.value.default_harness ? eligible(settings.value.default_harness) : !Object.keys(settings.value.harnesses).some(eligible)))
watch(() => props.open, async open => {
  const mine = ++generation
  if (!open) return
  loading.value = true; error.value = ''; settings.value = null
  try {
    const data = await fetchHarnessSettings()
    if (mine === generation) { catalog.value = data; settings.value = structuredClone(data.settings) }
  } catch (e) { if (mine === generation) error.value = errorText(e) }
  finally { if (mine === generation) loading.value = false }
}, { immediate: true })
function toggle(name: string, enabled: boolean) {
  if (!settings.value) return
  settings.value.harnesses[name]!.enabled = enabled
  if (!enabled && settings.value.default_harness === name) settings.value.default_harness = null
  if (!settings.value.default_harness) settings.value.default_harness = Object.keys(settings.value.harnesses).find(eligible) ?? null
}
async function test(name: string) {
  if (!settings.value || !catalog.value || testing.value) return
  const model = settings.value.harnesses[name]!.model
  testing.value = name; error.value = ''
  try {
    const thinking = settings.value.harnesses[name]!.thinking
    const result = thinking ? await testHarness(name, model, thinking) : await testHarness(name, model)
    catalog.value.tests ??= {}
    catalog.value.tests[name] ??= {}
    catalog.value.tests[name]![model] = result
    emit('tested')
    if (!result.ok && settings.value.default_harness === name) settings.value.default_harness = Object.keys(settings.value.harnesses).find(eligible) ?? null
  } catch (e) { error.value = errorText(e) }
  finally { testing.value = null }
}
async function save() {
  if (!canSave.value || !settings.value) return
  saving.value = true; error.value = ''
  try { await saveHarnessSettings(JSON.parse(JSON.stringify(settings.value))); emit('saved'); emit('close') }
  catch (e) { error.value = errorText(e) }
  finally { saving.value = false }
}
function chooseModel(model: string) {
  if (settings.value && modelPicker.value) {
    const name = modelPicker.value
    const choice = settings.value.harnesses[name]!
    choice.model = model
    if (!choice.thinking || !thinkingOptions(name).some(o => o.value === choice.thinking)) choice.thinking = defaultThinking(name, model)
  }
  modelPicker.value = null
}
</script>

<template>
  <ConfirmDialog :open="open && modelPicker === null" title="Harnessy tohoto počítače" confirm-label="Uložit nastavení" :confirm-disabled="!canSave" @confirm="save" @cancel="!saving && !testing && emit('close')">
    <p>Výchozí volby pro všechny factory na tomto počítači. Projekt a potom task mohou harness, model a thinking level přepsat.</p>
    <p v-if="loading"><Spinner /> Načítám harnessy a modely…</p>
    <p v-if="error" role="alert" data-test="machine-harness-error">{{ error }}</p>
    <div v-if="settings && catalog" class="harnesses" data-test="machine-harnesses">
      <fieldset v-for="(choice, name) in settings.harnesses" :key="name" :disabled="saving || !!testing" :data-harness="name">
        <legend>{{ name }}</legend>
        <p v-if="!catalog.available[name]">Na tomto počítači není nainstalovaný.</p>
        <label><input type="checkbox" role="switch" class="switch" :aria-label="`Zapnout ${name}`" :checked="choice.enabled" :disabled="!catalog.available[name] && !choice.enabled" :data-test="`machine-enabled-${name}`" @change="toggle(name, ($event.target as HTMLInputElement).checked)"> {{ choice.enabled ? 'Zapnutý' : 'Vypnutý' }}</label>
        <label><input v-model="settings.default_harness" type="radio" name="default-harness" :value="name" :disabled="!eligible(String(name))" :data-test="`machine-default-${name}`"> Výchozí harness</label>
        <button type="button" class="model-button" :aria-label="`Výchozí model ${name}`" :disabled="!catalog.available[name] || !choice.enabled" :data-test="`machine-model-${name}`" @click="modelPicker = String(name)"><span><small>Výchozí model</small>{{ choice.model || 'Vybrat model' }}</span><ChevronRight :size="18" aria-hidden="true" /></button>
        <button type="button" class="test-button" :disabled="!catalog.available[name] || !choice.model || !!testing" :data-test="`machine-test-${name}`" @click="test(String(name))"><Spinner v-if="testing === name" /><Play v-else :size="14" aria-hidden="true" /> {{ testing === name ? 'Testuji…' : 'Test' }}</button>
        <label class="thinking-choice"><span>Výchozí thinking level</span><SelectMenu :model-value="choice.thinking ?? ''" :options="thinkingOptions(String(name))" placeholder="Model nenabízí nastavení" :label="`Výchozí thinking level ${name}`" :disabled="!catalog.available[name] || !choice.enabled || saving || !!testing || thinkingOptions(String(name)).length < 2" :data-test="`machine-thinking-${name}`" @update:model-value="choice.thinking = $event" /></label>
        <p v-if="testResult(String(name))" :data-test="`machine-test-result-${name}`" :class="testResult(String(name))?.ok ? 'test-ok' : 'test-failed'" role="status">{{ testResult(String(name))?.ok ? 'Vše OK — harness odpověděl OK.' : testResult(String(name))?.error }}<span v-if="!testResult(String(name))?.ok"> Nelze použít jako výchozí; v topbaru se nezobrazí.</span></p>
      </fieldset>
    </div>
  </ConfirmDialog>
  <ModelPickerDialog :open="open && modelPicker !== null" :harness="modelPicker ?? ''" :models="catalog?.models[modelPicker ?? ''] ?? []" :model="settings?.harnesses[modelPicker ?? '']?.model ?? ''" @choose="chooseModel" @close="modelPicker = null" />
</template>

<style scoped>
.harnesses { display: flex; flex-direction: column; gap: 12px; max-height: 55vh; overflow-y: auto; }
fieldset { border: 1px solid var(--border); border-radius: 12px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; padding: 16px; background: var(--panel-2); }
fieldset > p { grid-column: 1 / -1; margin: 0; font-size: 13px; line-height: 1.5; }
legend { font-weight: 600; }
.test-ok { color: var(--green); }
.test-failed { color: var(--red); }
label { display: flex; align-items: center; gap: 8px; }
.thinking-choice { grid-column: 1 / -1; justify-content: space-between; font-size: 13px; }
.model-button { display: flex; align-items: center; justify-content: space-between; padding: 12px; border: 1px solid var(--border); background: var(--panel); color: var(--text); border-radius: 10px; font: inherit; text-align: left; }
.model-button span { display: flex; flex-direction: column; gap: 5px; }
.model-button small { color: var(--faint); font-size: 12px; }
.test-button { display: inline-flex; align-items: center; align-self: flex-start; gap: 7px; padding: 7px 13px; color: var(--cyan); border: 1px solid color-mix(in srgb, var(--cyan) 35%, var(--border)); background: color-mix(in srgb, var(--cyan) 8%, var(--panel)); border-radius: 8px; font: inherit; }
</style>
