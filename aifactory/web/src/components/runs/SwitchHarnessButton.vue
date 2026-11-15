<script setup lang="ts">
import { runError } from '@/lib/runMessages'
import { t } from '@/lib/i18n'
// „Pokračovat s jiným harnessem“ of a run that ran out of quota: a button that opens a small
// form with the harnesses this computer enabled and tested (GET /api/runs/{id}/harness-choices,
// never the exhausted one), then `factory task retry --harness` with the chosen one.
import { computed, ref } from 'vue'
import { Shuffle } from 'lucide-vue-next'
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
const errorSource = ref<(() => string) | null>(null)
const error = computed(() => errorSource.value?.() ?? null)
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
  errorSource.value = null
  try {
    choices.value = (await harnessChoices(props.runId)).choices
    selected.value = choices.value[0]?.harness ?? ''
  } catch (e) {
    choices.value = []
    errorSource.value = () => t('runs.harnessy_se_nepodarilo_nacist_p0', { p0: runError(e) })
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!selected.value) return
  busy.value = true
  errorSource.value = null
  try {
    const result = await retryOnHarness(props.runId, selected.value)
    open.value = false
    emit('started', result)
  } catch (e) {
    errorSource.value = () => t('runs.beh_se_nepodarilo_navazat_p0', { p0: runError(e) })
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
      <Shuffle :size="14" /> {{ t('runs.pokracovat_s_jinym_harnessem') }} </button>
    <form v-if="open" class="switch-form" data-test="switch-form" @submit.prevent="submit">
      <p v-if="loading" class="faint"><Spinner /> {{ t('runs.nacitam_harnessy') }}</p>
      <template v-else-if="choices.length">
        <SelectMenu v-model="selected" data-test="switch-select" :label="t('runs.harness')" :options="options" />
        <p class="faint hint"> {{ t('runs.vsichni_agenti_behu_pokracuji_na_vybranem_harnessu_od_faze_ktera_selhala_agent_bez_pu') }} </p>
        <div class="actions">
          <button
            type="submit"
            class="primary"
            data-test="switch-submit"
            :disabled="busy || !selected"
            :aria-busy="busy || undefined"
          >
            <Spinner v-if="busy" /> {{ t('runs.pokracovat') }} </button>
          <button type="button" data-test="switch-cancel" :disabled="busy" @click="open = false">{{ t('runs.zrusit') }}</button>
        </div>
      </template>
      <p v-else-if="!error" class="faint" data-test="switch-none"> {{ t('runs.zadny_jiny_harness_neni_povoleny_a_otestovany_povolte_a_otestujte_ho_v_nastaveni_stro') }} </p>
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
