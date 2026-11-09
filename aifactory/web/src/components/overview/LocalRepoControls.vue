<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import { fetchLegacyRepoSettings, importLegacyRepoSettings, patchLocalRepoSettings, type LegacyRepoPreview, type LocalRepoSettings, type OverviewRepo } from '@/lib/api'
import { errorText } from '@/lib/format'
import { fetchHarnessSettings, type HarnessCatalog } from '@/lib/machineHarnesses'

const props = defineProps<{ repo: OverviewRepo }>()
const emit = defineEmits<{ changed: [] }>()
const confirmed = ref(props.repo.local_settings ?? null)
const saving = ref(false)
const error = ref<string | null>(null)
const saved = ref(false)
const catalog = ref<HarnessCatalog | null>(null)
const catalogLoading = ref(true)
const catalogError = ref<string | null>(null)
const legacy = ref<LegacyRepoPreview | null>(null)
const choices = ref<Record<string, string>>({})
const overwrite = ref(false)
const importReady = computed(() => legacy.value && (!legacy.value.local_exists || overwrite.value)
  && Object.entries(legacy.value.proposals).every(([key, proposal]) => !proposal.conflict || choices.value[key] !== undefined))
async function previewLegacy() {
  error.value = null
  try {
    legacy.value = await fetchLegacyRepoSettings(props.repo.id)
    choices.value = {}
    overwrite.value = false
  } catch (e) { error.value = errorText(e) }
}
async function takeLegacy() {
  if (!importReady.value || saving.value) return
  saving.value = true
  error.value = null
  try {
    const selected = Object.fromEntries(Object.entries(choices.value).map(([key, value]) =>
      [key, key === 'harness' ? value || null : value === 'on']))
    confirmed.value = await importLegacyRepoSettings(props.repo.id, selected, overwrite.value)
    legacy.value = null
    saved.value = true
    emit('changed')
  } catch (e) { error.value = errorText(e) }
  finally { saving.value = false }
}
const harnessOptions = computed(() => Object.entries(catalog.value?.settings.harnesses ?? {})
  .filter(([name, choice]) => choice.enabled && catalog.value?.available[name])
  .map(([name]) => ({ value: name, label: name })))
const harnessChoices = computed(() => [
  { value: '', label: `Podle počítače (${catalog.value?.settings.default_harness ?? 'nenastaveno'})` },
  ...harnessOptions.value,
])
onMounted(async () => {
  try { catalog.value = await fetchHarnessSettings() }
  catch (e) { catalogError.value = errorText(e) }
  finally { catalogLoading.value = false }
})
watch(() => props.repo.local_settings, value => {
  if (!saving.value) confirmed.value = value ?? null
})
const harnessUnavailable = computed(() => {
  const name = confirmed.value?.effective_harness
  return name && catalog.value && !harnessOptions.value.some(o => o.value === name)
})

async function save(changes: Partial<LocalRepoSettings['settings']>) {
  if (saving.value) return
  saving.value = true
  saved.value = false
  error.value = null
  try {
    confirmed.value = await patchLocalRepoSettings(props.repo.id, changes)
    saved.value = true
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = false
    emit('changed')
  }
}

function toggle(key: 'auto_merge' | 'auto_continue', event: Event) {
  const input = event.target as HTMLInputElement
  const value = input.checked
  // Keep the DOM on the confirmed value until the write succeeds.
  input.checked = confirmed.value?.settings[key] ?? false
  void save({ [key]: value })
}
function harness(value: string) {
  void save({ harness: value || null })
}
</script>

<template>
  <section class="local-controls" data-test="local-repo-controls" :aria-label="`Na tomto počítači: ${repo.name}`">
    <strong>Na tomto počítači</strong>
    <p>Platí pouze pro novou Factory na tomto počítači. Ukládá se ihned.</p>
    <p>Staré volby v backlogu nová Factory nepoužívá. Bez místních voleb jsou automatizace vypnuté.</p>
    <button type="button" data-test="legacy-preview" :disabled="saving" @click="previewLegacy">Náhled starých voleb</button>
    <div v-if="legacy" class="legacy-panel" data-test="legacy-panel">
      <p>Náhled frontmatterů; převzetí mění jen tento počítač. Model a thinking zůstávají metadata, harness použije místní nastavení.</p>
      <table>
        <thead><tr><th>Úroveň / ID</th><th>Auto merge</th><th>Auto continue</th><th>Harness</th><th>Model</th><th>Thinking</th></tr></thead>
        <tbody><tr v-for="node in legacy.nodes" :key="node.id"><td>{{ node.level }} / {{ node.id }}</td><td v-for="key in ['auto_merge', 'auto_continue', 'harness', 'model', 'thinking']" :key="key"><Tooltip :text="JSON.stringify(node.values[key]?.origin ?? null)"><span tabindex="0">{{ node.values[key]?.value ?? 'dědí / nenastaveno' }}</span></Tooltip></td></tr></tbody>
      </table>
      <div v-for="(proposal, key) in legacy.proposals" :key="key">
        <div v-if="proposal.conflict" class="legacy-choice">
          <span>{{ key }}: rozdílné hodnoty, zvolte pro celé repo</span>
          <SelectMenu
            :data-test="`legacy-choice-${key}`"
            :model-value="choices[key] ?? '__unset__'"
            :options="key === 'harness' ? [{ value: '', label: 'Podle počítače' }, ...harnessOptions] : [{ value: 'on', label: 'Zapnuto' }, { value: 'off', label: 'Vypnuto' }]"
            :label="`${key}: volba pro celé repo`"
            placeholder="Vyberte…"
            :disabled="saving"
            @update:model-value="choices[key] = $event"
          />
        </div>
        <p v-else>{{ key }}: {{ proposal.value ?? 'podle počítače' }}</p>
      </div>
      <label v-if="legacy.local_exists"><input v-model="overwrite" type="checkbox" data-test="legacy-overwrite" />Výslovně přepsat existující místní volby</label>
      <button type="button" data-test="legacy-import" :disabled="!importReady || saving" @click="takeLegacy">Převzít na tomto počítači</button>
    </div>
    <fieldset :disabled="saving || !confirmed" :aria-busy="saving">
      <legend>Automatizace a výchozí harness</legend>
      <label><input type="checkbox" data-test="local-auto-merge" :checked="confirmed?.settings.auto_merge ?? false" @change="toggle('auto_merge', $event)" /> Auto merge</label>
      <label><input type="checkbox" data-test="local-auto-continue" :checked="confirmed?.settings.auto_continue ?? false" @change="toggle('auto_continue', $event)" /> Auto continue</label>
      <div class="harness-field">
        <span>Výchozí harness</span>
        <SelectMenu
          data-test="local-harness"
          :model-value="confirmed?.settings.harness ?? ''"
          :options="harnessChoices"
          label="Výchozí harness"
          :placeholder="confirmed?.settings.harness ? `${confirmed.settings.harness} (nedostupný)` : ''"
          :disabled="saving || !confirmed || !catalog"
          @update:model-value="harness"
        />
      </div>
    </fieldset>
    <p v-if="confirmed && !confirmed.settings.auto_continue" data-test="local-off-note">Aktuální běhy doběhnou, další se nespustí</p>
    <p v-if="catalogLoading">Načítám katalog harnessů…</p>
    <p v-else-if="catalogError" role="alert">Katalog harnessů není dostupný: {{ catalogError }}</p>
    <p v-if="harnessUnavailable" role="alert">Výchozí harness není na tomto počítači dostupný a zapnutý.</p>
    <p role="status" aria-live="polite">{{ saving ? 'Ukládání…' : saved ? 'Uloženo' : '' }}</p>
    <p v-if="error || repo.local_settings_error || !confirmed" role="alert">{{ error || repo.local_settings_error || 'Místní volby nejsou pro toto repo dostupné.' }}</p>
  </section>
</template>

<style scoped>
.local-controls { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
p { margin: 0; color: var(--dim); }
fieldset { display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid var(--border); border-radius: 6px; }
label, .harness-field { display: flex; align-items: center; gap: 6px; }
[role='alert'] { color: var(--red); }
.legacy-panel { max-width: 100%; overflow-x: auto; }
th, td { padding: 4px 8px; text-align: left; vertical-align: top; }
</style>
