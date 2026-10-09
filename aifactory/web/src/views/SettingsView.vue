<script setup lang="ts">
import { errorText } from '../lib/format'
// Settings: shared .factory/config.yaml and local .factory/local.yaml (nothing is committed).
import { onMounted, ref } from 'vue'
import { ApiError } from '@/lib/api'
import { useConfigStatus } from '@/lib/configStatus'
import { fetchSettings, fieldErrors, saveSettings, type SettingsData, type SettingsSaveInput } from '@/lib/settings'
import SettingsForm from '@/components/settings/SettingsForm.vue'
import ProjectSettings from '@/components/settings/ProjectSettings.vue'

const configStatus = useConfigStatus()

const settings = ref<SettingsData | null>(null)
const loading = ref(true)
const loadError = ref<string | null>(null)
const busy = ref(false)
const errors = ref<Record<string, string[]>>({})
const saved = ref(false)
// a new key re-mounts the form with the saved values; after a failed save it keeps the input
const formKey = ref(0)

function message(err: unknown): string {
  return errorText(err)
}

async function load(): Promise<void> {
  loading.value = true
  try {
    settings.value = await fetchSettings()
    loadError.value = null
  } catch (err) {
    loadError.value = message(err)
  } finally {
    loading.value = false
  }
}

async function projectSaved(): Promise<void> {
  await load()
  saved.value = true
  await configStatus.refresh()
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
  } catch (err) {
    if (err instanceof ApiError && err.code === 'invalid_value' && err.issues.length) {
      errors.value = fieldErrors(err.issues)
    } else {
      errors.value = { '': [message(err)] }
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
  <section class="settings-view">
    <div class="view-head">
      <h1>Nastavení</h1>
      <span v-if="saved" class="saved" data-test="saved">Uloženo</span>
    </div>
    <p v-if="settings?.repository" class="faint" data-test="repository">Repozitář: {{ settings.repository }}</p>
    <p class="intro">
      Sdílené hodnoty se ukládají do pracovního stromu a běhy je použijí až po commitu do
      <code>{{ settings?.shared.base ?? 'base' }}</code>. Lokální hodnoty zůstávají jen na tomto stroji.
    </p>
    <p v-if="loadError" class="error-bar" data-test="error">{{ loadError }}</p>
    <SettingsForm
      v-if="settings"
      :key="formKey"
      :settings="settings"
      :busy="busy"
      :errors="errors"
      @submit="onSubmit"
      @reset="onReset"
    />
    <ProjectSettings v-if="settings" :settings="settings" @saved="projectSaved" />
    <p v-else-if="loading" class="faint">Načítám…</p>
  </section>
</template>

<style scoped>
.settings-view {
  padding: 28px;
  max-width: 1200px;
  margin: 0 auto;
}

.view-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin-bottom: 12px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
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
