<script setup lang="ts">
import { t } from '@/lib/i18n'
// One finding of the machine check on #/setup: severity and code, the message and its fix
// with a copy button. The dashboard gets only findings with a fix or an action.
import { ref } from 'vue'
import type { CheckFinding } from '@/lib/api'
import { findingText } from '@/lib/factoryMessages'
import { machineFixText } from '@/lib/setupMessages'
import { errorText } from '@/lib/format'

defineProps<{ finding: CheckFinding }>()

const copied = ref(false)
const copyError = ref('')

async function copy(text: string) {
  copyError.value = ''
  try { await navigator.clipboard.writeText(text); copied.value = true }
  catch (e) { copyError.value = errorText(e) }
}
</script>
<template>
  <article :class="finding.severity" data-test="machine-finding">
    <strong>{{ finding.severity === 'info' ? 'info' : t(`setup.${finding.severity}`) }} · {{ finding.code }}</strong><p>{{ findingText(finding.code) }}</p>
    <template v-if="finding.fix">
      <p>{{ machineFixText(finding.code) }}</p>
      <button data-test="copy-fix" @click="copy(finding.fix)">{{ copied ? t('setup.copied') : t('setup.copy') }}</button>
      <span v-if="copyError" role="alert">{{ copyError }}</span>
    </template>
    <details><summary>{{ t('dashboard.diagnostics') }}</summary><p>{{ finding.message }}</p><pre v-if="finding.fix">{{ finding.fix }}</pre></details>
  </article>
</template>
