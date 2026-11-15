<script setup lang="ts">
import { t } from '@/lib/i18n'
import { backlogError } from '@/lib/backlogMessages'
import { flattenIssues } from '@/lib/backlog'
import { fmtMoney4, fmtNumber } from '@/lib/format'
import { onBeforeUnmount, ref, watch } from 'vue'
import { Wand2 } from 'lucide-vue-next'
import { getApi, postApi } from '@/lib/api'
import { currentRepoId } from '@/lib/router'
import Spinner from '@/components/ui/Spinner.vue'

export interface Recommendation {
  workflow_name: string
  decision: 'existing' | 'new'
  reason: string
  warnings?: string[]
  workflow_yaml: string | null
  outline: { name?: string; step?: string; kind?: string; agent?: string; max?: number }[]
}
/** Tokens and price of one proposal, as the provider reported them. */
export interface AdviceUsage {
  tokens: number
  cost_usd: number | null
}
interface Job {
  job_id: string
  state: 'queued' | 'running' | 'succeeded' | 'failed'
  recommendation: (Recommendation & { usage?: AdviceUsage | null }) | null
  error: string | null
  error_code?: string | null
  usage?: AdviceUsage | null
}
const props = defineProps<{ draft: Record<string, unknown>; taskId?: string; disabled?: boolean }>()
const emit = defineEmits<{
  result: [result: Recommendation, jobId: string]
  busy: [value: boolean]
  invalidate: []
}>()
const busy = ref(false)
const error = ref<string | (() => string)>('')
const errorDetail = ref<string | null>(null)
const result = ref<Recommendation | null>(null)
/** The cost of every finished proposal of this form (null: the provider reported none). */
const costs = ref<(AdviceUsage | null)[]>([])
function costText(cost: AdviceUsage | null): string {
  if (!cost) return t('backlog.provider_naklady_nevykazal')
  const price = cost.cost_usd == null ? t('backlog.provider_cenu_nevykazal') : fmtMoney4(cost.cost_usd)
  return t('backlog.tokenUsage', { price, count: fmtNumber(cost.tokens) }, cost.tokens)
}
let requestedDraft = ''
let requestedTaskId: string | undefined
let generation = 0
let controller: AbortController | undefined
let timer: ReturnType<typeof setTimeout> | undefined
function stop() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  busy.value = false
  emit('busy', false)
}
function withoutWorkflow(draft: Record<string, unknown>) {
  const { workflow: _workflow, ...inputs } = draft
  return JSON.stringify(inputs)
}
watch(() => JSON.stringify([props.taskId, props.draft]), () => {
  // Applying our selection changes only workflow; keep its explanation and save reference.
  if (result.value && props.taskId === requestedTaskId && props.draft.workflow === result.value.workflow_name &&
      withoutWorkflow(props.draft) === requestedDraft) return
  if (busy.value) {
    errorDetail.value = null
    error.value = () => t('backlog.zadani_se_zmenilo_spust_navrh_znovu')
  }
  stop()
  result.value = null
  emit('invalidate')
})
let repoScope = currentRepoId()
function scopeChanged() {
  if (repoScope === currentRepoId()) return
  repoScope = currentRepoId()
  stop()
  result.value = null
  costs.value = []
  emit('invalidate')
}
window.addEventListener('hashchange', scopeChanged)
onBeforeUnmount(() => {
  stop()
  window.removeEventListener('hashchange', scopeChanged)
})
async function start() {
  if (busy.value || props.disabled) return
  stop()
  requestedDraft = withoutWorkflow(props.draft)
  requestedTaskId = props.taskId
  const token = generation
  const scope = currentRepoId()
  controller = new AbortController()
  result.value = null
  errorDetail.value = null
  error.value = ''
  emit('invalidate')
  busy.value = true
  emit('busy', true)
  const active = () => token === generation && scope === currentRepoId()
  const fail = (e: unknown) => {
    if (!active()) return
    errorDetail.value = null
    error.value = () => e instanceof Error ? backlogError(flattenIssues(e)) : t('backlog.navrh_workflow_selhal_zkus_to_znovu')
    stop()
  }
  const poll = async (id: string) => {
    if (!active()) return
    try {
      const job = await getApi<Job>(`/backlog/workflow-advice/${encodeURIComponent(id)}`, controller?.signal)
      if (!active()) return
      if (job.state === 'failed') {
        errorDetail.value = job.error_code === 'advice_invalid' ? job.error : null
        error.value = () => backlogError({ code: job.error_code ?? undefined, message: job.error || t('backlog.navrh_workflow_selhal') })
        costs.value.push(job.usage ?? null)
        stop()
        return
      }
      if (job.state === 'succeeded' && job.recommendation) {
        result.value = job.recommendation
        costs.value.push(job.usage ?? job.recommendation.usage ?? null)
        stop()
        emit('result', job.recommendation, id)
      } else timer = setTimeout(() => void poll(id), 800)
    } catch (e) { fail(e) }
  }
  try {
    const job = await postApi<Job>('/backlog/workflow-advice', {
      ...(props.taskId ? { task_id: props.taskId } : {}), draft: props.draft,
    }, controller.signal)
    if (active()) await poll(job.job_id)
  } catch (e) { fail(e) }
}
defineExpose({ start })
</script>

<template>
  <div class="workflow-advice" data-test="workflow-advice">
    <button type="button" :disabled="disabled || busy" @click="start">
      <Spinner v-if="busy" />
      <Wand2 v-else :size="16" aria-hidden="true" />
      {{ busy ? t('backlog.agent_vybira_workflow') : t('backlog.suggestWorkflow') }}
    </button>
    <p v-if="error" role="alert">{{ typeof error === 'function' ? error() : error }}</p>
    <details v-if="error && errorDetail" data-test="advice-error-details">
      <summary>{{ t('dashboard.diagnostics') }}</summary>
      <pre>{{ errorDetail }}</pre>
    </details>
    <p v-for="(cost, index) in costs" :key="index" data-test="workflow-advice-cost">
      {{ t('backlog.navrh') }} {{ index + 1 }}: {{ costText(cost) }}
    </p>
    <div v-if="result" data-test="advice-result">
      <strong>{{ result.workflow_name }}</strong>
      · {{ result.decision === 'new' ? t('backlog.nove_workflow') : t('backlog.existujici_workflow') }}
      <p>{{ result.reason }}</p>
      <p v-for="warning in result.warnings" :key="warning" class="faint">{{ warning }}</p>
      <ul><li v-for="(item, index) in result.outline" :key="index">{{ item.step || item.name || item.kind }}{{ item.agent ? ` · ${item.agent}` : '' }}{{ item.max ? ` (max ${item.max})` : '' }}</li></ul>
      <details v-if="result.workflow_yaml"><summary>{{ t('backlog.yaml_workflow') }}</summary><pre>{{ result.workflow_yaml }}</pre></details>
    </div>
  </div>
</template>

<style scoped>
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
.workflow-advice { display: flex; flex-direction: column; gap: 10px; }
button {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}
button:disabled { opacity: 0.5; cursor: default; }
[role='alert'] { color: var(--red); }
summary { cursor: pointer; }
</style>
