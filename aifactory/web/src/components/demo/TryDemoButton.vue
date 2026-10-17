<script setup lang="ts">
// "Vyzkoušet na ukázce": creates the sample repository, starts its first task with the first
// tested harness and opens its backlog on that task (lib/demo.ts).
import { ref } from 'vue'
import { FlaskConical } from 'lucide-vue-next'
import { DEMO_TASK, startDemo } from '@/lib/demo'
import { errorText } from '@/lib/format'
import { repoHref } from '@/lib/router'
import Spinner from '@/components/ui/Spinner.vue'

const emit = defineEmits<{ started: [repoId: string] }>()
const busy = ref(false)
const error = ref<string | null>(null)

async function run() {
  busy.value = true
  error.value = null
  try {
    const result = await startDemo()
    window.dispatchEvent(new Event('factory-applied'))
    emit('started', result.repoId)
    window.location.hash = repoHref(result.repoId, 'backlog', DEMO_TASK)
  } catch (err) {
    error.value = errorText(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="try-demo">
    <button type="button" class="try-button" :disabled="busy" :aria-busy="busy || undefined" data-test="try-demo" @click="run">
      <Spinner v-if="busy" /><FlaskConical v-else :size="14" aria-hidden="true" />
      {{ busy ? 'Připravuji ukázku…' : 'Vyzkoušet na ukázce' }}
    </button>
    <span v-if="error" class="try-error" role="alert" data-test="try-demo-error">Ukázku se nepodařilo připravit: {{ error }}</span>
  </span>
</template>

<style scoped>
.try-demo { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.try-button { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--cyan); font: inherit; font-weight: 600; cursor: pointer; }
.try-button:disabled { cursor: default; opacity: 0.7; }
.try-error { color: var(--red); }
</style>
