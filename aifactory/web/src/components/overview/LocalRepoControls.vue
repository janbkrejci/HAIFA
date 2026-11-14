<script setup lang="ts">
import { t } from '@/lib/i18n'
import { deferredError } from '@/lib/dashboardMessages'
import { feedbackText } from '@/components/overview/feedback'
import { computed, onMounted, ref, watch } from 'vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import { patchLocalRepoSettings, type LocalRepoSettings, type OverviewRepo } from '@/lib/api'
import { fetchHarnessSettings, type HarnessCatalog } from '@/lib/machineHarnesses'

const props = defineProps<{ repo: OverviewRepo }>()
const emit = defineEmits<{ changed: [] }>()
const confirmed = ref(props.repo.local_settings ?? null)
const saving = ref(false)
const error = ref<string | (() => string) | null>(null)
const saved = ref(false)
const catalog = ref<HarnessCatalog | null>(null)
const catalogLoading = ref(true)
const catalogError = ref<string | (() => string) | null>(null)
const harnessOptions = computed(() => Object.entries(catalog.value?.settings.harnesses ?? {})
  .filter(([name, choice]) => choice.enabled && catalog.value?.available[name])
  .map(([name]) => ({ value: name, label: name })))
const harnessChoices = computed(() => [
  { value: '', label: t('dashboard.inheritHarness', { harness: catalog.value?.settings.default_harness ?? t('dashboard.unset') }) },
  ...harnessOptions.value,
])
onMounted(async () => {
  try { catalog.value = await fetchHarnessSettings() }
  catch (e) { catalogError.value = deferredError(e) }
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
    error.value = deferredError(e)
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
  <section class="local-controls" data-test="local-repo-controls" :aria-label="t('dashboard.onComputer', { name: repo.name })">
    <fieldset :disabled="saving || !confirmed" :aria-busy="saving">
      <legend>{{ t('dashboard.localLegend') }}</legend>
      <label><input type="checkbox" data-test="local-auto-merge" :checked="confirmed?.settings.auto_merge ?? false" @change="toggle('auto_merge', $event)" /> Auto merge</label>
      <label><input type="checkbox" data-test="local-auto-continue" :checked="confirmed?.settings.auto_continue ?? false" @change="toggle('auto_continue', $event)" /> Auto continue</label>
      <div class="harness-field">
        <span>{{ t('dashboard.defaultHarness') }}</span>
        <SelectMenu
          data-test="local-harness"
          :model-value="confirmed?.settings.harness ?? ''"
          :options="harnessChoices"
          :label="t('dashboard.defaultHarness')"
          :placeholder="confirmed?.settings.harness ? t('dashboard.unavailableHarness', { harness: confirmed.settings.harness }) : ''"
          :disabled="saving || !confirmed || !catalog"
          @update:model-value="harness"
        />
      </div>
    </fieldset>
    <p v-if="catalogLoading">{{ t('dashboard.catalogLoading') }}</p>
    <p v-else-if="catalogError" role="alert">{{ t('dashboard.catalogFailed') }} {{ feedbackText(catalogError) }}</p>
    <p v-if="harnessUnavailable" role="alert">{{ t('dashboard.harnessUnavailable') }}</p>
    <p role="status" aria-live="polite">{{ saving ? t('dashboard.saving') : saved ? t('dashboard.saved') : '' }}</p>
    <p v-if="error || repo.local_settings_error || !confirmed" role="alert">{{ feedbackText(error) || (repo.local_settings_error_code ? t('dashboard.localSettingsError', { code: repo.local_settings_error_code }) : t('dashboard.localUnavailable')) }}</p>
    <details v-if="repo.local_settings_error"><summary>{{ t('dashboard.diagnostics') }}</summary><pre>{{ repo.local_settings_error }}</pre></details>
  </section>
</template>

<style scoped>
.local-controls { display: flex; flex-direction: column; gap: 6px; font-size: 13px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
p { margin: 0; color: var(--dim); }
fieldset { display: flex; flex-wrap: wrap; gap: 12px; border: 1px solid var(--border); border-radius: 6px; }
label, .harness-field { display: flex; align-items: center; gap: 6px; }
[role='alert'] { color: var(--red); }
</style>
