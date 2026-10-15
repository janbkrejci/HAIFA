<script setup lang="ts">
// The repo settings section of the Factory screen (#/r/<id>/factory/settings): shared
// .factory/config.yaml and local .factory/local.yaml. Nothing is committed here; a saved
// shared value shows as uncommitted configuration and is committed on the same screen.
import { onMounted, ref } from 'vue'
import { ApiError } from '@/lib/api'
import { useConfigStatus } from '@/lib/configStatus'
import { errorText } from '@/lib/format'
import { fetchSettings, fieldErrors, saveSettings, type SettingsData, type SettingsSaveInput } from '@/lib/settings'
import SettingsForm from '@/components/settings/SettingsForm.vue'

const emit = defineEmits<{ saved: [] }>()

const configStatus = useConfigStatus()

const settings = ref<SettingsData | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const busy = ref(false)
const errors = ref<Record<string, string[]>>({})
const saved = ref(false)
// a new key re-mounts the form with the saved values; after a failed save it keeps the input
const formKey = ref(0)

async function load(): Promise<void> {
  loading.value = true
  try {
    settings.value = await fetchSettings()
    loadError.value = null
  } catch (err) {
    loadError.value = errorText(err)
  } finally {
    loading.value = false
  }
}

async function onSubmit(input: SettingsSaveInput): Promise<void> {
  busy.value = true
  saved.value = false
  try {
    settings.value = await saveSettings(input)
    errors.value = {}
    saved.value = true
    formKey.value += 1
    await configStatus.refresh()
    emit('saved')
  } catch (err) {
    if (err instanceof ApiError && err.code === 'invalid_value' && err.issues.length) {
      errors.value = fieldErrors(err.issues)
    } else {
      errors.value = { '': [errorText(err)] }
    }
  } finally {
    busy.value = false
  }
}

function onReset(): void {
  errors.value = {}
  saved.value = false
}

onMounted(load)
</script>

<template>
  <section class="repo-settings" data-test="repo-settings">
    <div class="section-head">
      <h2>Nastavení repozitáře</h2>
      <span v-if="saved" class="saved" data-test="saved">Uloženo</span>
    </div>
    <p class="intro">
      Sdílené hodnoty se ukládají do pracovního stromu a běhy je použijí až po commitu do
      <code>{{ settings?.shared?.base ?? 'base' }}</code> (červený čip „Necommitnutá konfigurace“ v horní liště). Lokální hodnoty zůstávají jen na tomto stroji.
    </p>
    <p v-if="loadError" class="error-bar" data-test="error">{{ loadError }}</p>
    <SettingsForm
      v-if="settings?.shared"
      :key="formKey"
      :settings="settings"
      :busy="busy"
      :errors="errors"
      @submit="onSubmit"
      @reset="onReset"
    />
    <p v-else-if="loading" class="faint">Načítám…</p>
  </section>
</template>

<style scoped>
.repo-settings {
  margin-top: 28px;
}

.section-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 8px;
}

h2 {
  margin: 0;
  color: var(--dim);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.intro {
  margin: 0 0 18px;
  color: var(--dim);
  max-width: 760px;
}

.saved {
  color: var(--green);
}
</style>
