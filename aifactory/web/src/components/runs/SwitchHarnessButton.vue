<script setup lang="ts">
// „Pokračovat s jiným harnessem“ of a run that ran out of quota: a button that opens a small
// form with the harnesses this computer enabled and tested (GET /api/runs/{id}/harness-choices,
// never the exhausted one), then `factory task retry --harness` with the chosen one.
import { computed, ref } from 'vue'
import { Shuffle } from 'lucide-vue-next'
import { errorText } from '@/lib/format'
import { harnessChoices, retryOnHarness, type HarnessChoice, type RetryResponse } from '@/lib/runs'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ runId: string }>()
const emit = defineEmits<{ started: [result: RetryResponse] }>()

const open = ref(false)
const loading = ref(false)
const choices = ref<HarnessChoice[]>([])
const selected = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const options = computed(() =>
  choices.value.map((c) => ({
    value: c.harness,
    label: `${c.harness} · ${c.model}${c.thinking ? ` · ${c.thinking}` : ''}`,
  })),
)

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  loading.value = true
  error.value = null
  try {
    choices.value = (await harnessChoices(props.runId)).choices
    selected.value = choices.value[0]?.harness ?? ''
  } catch (e) {
    choices.value = []
    error.value = `Harnessy se nepodařilo načíst: ${errorText(e)}`
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!selected.value) return
  busy.value = true
  error.value = null
  try {
    const result = await retryOnHarness(props.runId, selected.value)
    open.value = false
    emit('started', result)
  } catch (e) {
    error.value = `Běh se nepodařilo navázat: ${errorText(e)}`
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="switch">
    <button
      type="button"
      class="switch-open"
      data-test="switch-harness"
      :disabled="busy"
      :aria-expanded="open"
      @click="toggle"
    >
      <Shuffle :size="14" /> Pokračovat s jiným harnessem
    </button>
    <form v-if="open" class="switch-form" data-test="switch-form" @submit.prevent="submit">
      <p v-if="loading" class="faint"><Spinner /> Načítám harnessy…</p>
      <template v-else-if="choices.length">
        <SelectMenu v-model="selected" data-test="switch-select" label="Harness" :options="options" />
        <p class="faint hint">
          Všichni agenti běhu pokračují na vybraném harnessu od fáze, která selhala. Agent bez
          původní session dostane shrnutí hotové práce. Přepnutí se zapíše do běhu i do PR.
        </p>
        <div class="actions">
          <button
            type="submit"
            class="primary"
            data-test="switch-submit"
            :disabled="busy || !selected"
            :aria-busy="busy || undefined"
          >
            <Spinner v-if="busy" /> Pokračovat
          </button>
          <button type="button" data-test="switch-cancel" :disabled="busy" @click="open = false">Zrušit</button>
        </div>
      </template>
      <p v-else-if="!error" class="faint" data-test="switch-none">
        Žádný jiný harness není povolený a otestovaný. Povolte a otestujte ho v nastavení Stroje.
      </p>
      <p v-if="error" class="error" data-test="switch-error">{{ error }}</p>
    </form>
  </span>
</template>

<style scoped>
.switch {
  position: relative;
  display: inline-flex;
}

.switch-open {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.switch-form {
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
}
</style>
