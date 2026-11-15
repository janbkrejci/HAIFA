<script setup lang="ts">
import { t } from '@/lib/i18n'
// The repo settings section of the Factory screen (#/r/<id>/factory/settings): shared
// .factory/config.yaml and local .factory/local.yaml. Nothing is committed here; a saved
// shared value shows as uncommitted configuration and is committed on the same screen.
import { computed, onMounted, ref } from 'vue'
import { ApiError, type ApiIssue } from '@/lib/api'
import { useConfigStatus } from '@/lib/configStatus'
import { factoryDiagnostic, factoryErrorText, settingsIssueText } from '@/lib/factoryMessages'
import { fetchSettings, fieldErrors, saveSettings, type SettingsData, type SettingsSaveInput } from '@/lib/settings'
import SettingsForm from '@/components/settings/SettingsForm.vue'
import CollapsibleSection from '@/components/ui/CollapsibleSection.vue'

const emit = defineEmits<{ saved: [] }>()
const open = defineModel<boolean>('open', { default: true })

const configStatus = useConfigStatus()

const settings = ref<SettingsData | null>(null)
const loading = ref(true)
const loadError = ref<unknown>(null)
const busy = ref(false)
const issues = ref<ApiIssue[]>([])
const saveError = ref<unknown>(null)
const errors = computed((): Record<string, string[]> => {
  if (issues.value.length) return fieldErrors(issues.value, settingsIssueText)
  if (saveError.value) return { '': [factoryErrorText(saveError.value)] }
  return {}
})
const saved = ref(false)
// a new key re-mounts the form with the saved values; after a failed save it keeps the input
const formKey = ref(0)

async function load(): Promise<void> {
  loading.value = true
  try {
    settings.value = await fetchSettings()
    loadError.value = null
  } catch (err) {
    loadError.value = err
  } finally {
    loading.value = false
  }
}

async function onSubmit(input: SettingsSaveInput): Promise<void> {
  busy.value = true
  saved.value = false
  try {
    settings.value = await saveSettings(input)
    issues.value = []
    saveError.value = null
    saved.value = true
    formKey.value += 1
    await configStatus.refresh()
    emit('saved')
  } catch (err) {
    if (err instanceof ApiError && err.code === 'invalid_value' && err.issues.length) {
      issues.value = err.issues
      saveError.value = null
    } else {
      issues.value = []
      saveError.value = err
    }
  } finally {
    busy.value = false
  }
}

function onReset(): void {
  issues.value = []
  saveError.value = null
  saved.value = false
}

onMounted(load)
</script>

<template>
  <CollapsibleSection v-model:open="open" :heading="t('factoryUi.repoSettings')" class="repo-settings" data-test="repo-settings">
    <template #aside><span v-if="saved" class="saved" data-test="saved">{{ t('factoryUi.saved') }}</span></template>
    <p class="intro">
      {{ t('factoryUi.sharedIntro') }}
      <code>{{ settings?.shared?.base ?? 'base' }}</code> {{ t('factoryUi.localIntro') }}
    </p>
    <p v-if="loadError" class="error-bar" data-test="error">{{ factoryErrorText(loadError) }}</p>
    <details v-if="loadError"><summary>{{ t('factoryUi.technical') }}</summary>{{ factoryDiagnostic(loadError) }}</details>
    <details v-if="issues.length"><summary>{{ t('factoryUi.technical') }}</summary>
      <p v-for="(issue, i) in issues" :key="i">{{ issue.path }}: {{ issue.message }}</p>
    </details>
    <SettingsForm
      v-if="settings?.shared"
      :key="formKey"
      :settings="settings"
      :busy="busy"
      :errors="errors"
      @submit="onSubmit"
      @reset="onReset"
    />
    <p v-else-if="loading" class="faint">{{ t('factoryUi.loading') }}</p>
  </CollapsibleSection>
</template>

<style scoped>
.repo-settings {
  margin-top: 28px;
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
