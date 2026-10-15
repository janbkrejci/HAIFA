<script setup lang="ts">
// One finding of the machine check on #/setup: severity and code, the message and its fix
// with a copy button. The dashboard gets only findings with a fix or an action.
import { ref } from 'vue'
import type { CheckFinding, CheckSeverity } from '@/lib/api'
import { errorText } from '@/lib/format'

defineProps<{ finding: CheckFinding }>()

const SEVERITY_TEXT: Record<CheckSeverity, string> = { error: 'chyba', warning: 'varování', info: 'info' }
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
    <strong>{{ SEVERITY_TEXT[finding.severity] ?? finding.severity }} · {{ finding.code }}</strong><p>{{ finding.message }}</p>
    <template v-if="finding.fix">
      <p>{{ finding.fix }}</p>
      <button data-test="copy-fix" @click="copy(finding.fix)">{{ copied ? 'Zkopírováno' : 'Kopírovat' }}</button>
      <span v-if="copyError" role="alert">{{ copyError }}</span>
    </template>
  </article>
</template>
