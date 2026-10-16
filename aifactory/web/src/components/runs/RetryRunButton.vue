<script setup lang="ts">
// `factory task retry` of a failed, stopped or aborted run: a button that opens a small
// form with an optional note for the agents of the continuing phases.
import { ref } from 'vue'
import { RotateCcw } from 'lucide-vue-next'
import { errorText } from '@/lib/format'
import { retryRun, type RetryResponse } from '@/lib/runs'
import Spinner from '@/components/ui/Spinner.vue'

// `label`: the text of the button (the failure card says Pokračovat)
const props = withDefaults(defineProps<{ runId: string; label?: string }>(), { label: 'Navázat' })
const emit = defineEmits<{ started: [result: RetryResponse] }>()

const open = ref(false)
const note = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

async function submit() {
  busy.value = true
  error.value = null
  try {
    const result = await retryRun(props.runId, note.value)
    open.value = false
    note.value = ''
    emit('started', result)
  } catch (e) {
    error.value = `Běh se nepodařilo navázat: ${errorText(e)}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="retry">
    <button
      type="button"
      class="retry-open"
      data-test="retry-run"
      :disabled="busy"
      :aria-expanded="open"
      @click="open = !open"
    >
      <RotateCcw :size="14" /> {{ label }}
    </button>
    <form v-if="open" class="retry-form" data-test="retry-form" @submit.prevent="submit">
      <label>
        Poznámka pro agenty (volitelná)
        <textarea v-model="note" rows="3" data-test="retry-note" />
      </label>
      <p class="faint hint">
        Pokračuje ve stejném worktree a větvi od fáze, která selhala nebo byla zastavená. Hotové
        fáze se neopakují, agenti navážou na své sessions.
      </p>
      <div class="actions">
        <button type="submit" class="primary" data-test="retry-submit" :disabled="busy" :aria-busy="busy || undefined">
          <Spinner v-if="busy" /> {{ label }}
        </button>
        <button type="button" data-test="retry-cancel" :disabled="busy" @click="open = false">Zrušit</button>
      </div>
      <p v-if="error" class="error" data-test="retry-error">{{ error }}</p>
    </form>
  </span>
</template>

<style scoped>
.retry {
  position: relative;
  display: inline-flex;
}

.retry-open {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.retry-form {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: var(--z-dropdown);
  width: 340px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  box-shadow: var(--shadow-pop);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.retry-form label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 13px;
}

.retry-form textarea {
  font: inherit;
  resize: vertical;
}

.hint {
  margin: 0;
  font-size: 12px;
}

.actions {
  display: flex;
  gap: 8px;
}

.error {
  margin: 0;
  color: var(--red);
  font-size: 13px;
}
</style>
