<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
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
  usage?: AdviceUsage | null
}
const props = defineProps<{ draft: Record<string, unknown>; taskId?: string; disabled?: boolean }>()
const emit = defineEmits<{
  result: [result: Recommendation, jobId: string]
  busy: [value: boolean]
  invalidate: []
}>()
const busy = ref(false)
const error = ref('')
const result = ref<Recommendation | null>(null)
/** The cost of every finished proposal of this form (null: the provider reported none). */
const costs = ref<(AdviceUsage | null)[]>([])
function costText(cost: AdviceUsage | null): string {
  if (!cost) return 'Provider náklady nevykázal.'
  const price = cost.cost_usd == null ? 'Provider cenu nevykázal' : `$${cost.cost_usd.toFixed(4)} USD`
  return `${price} · ${cost.tokens} tokenů (vykázané providerem)`
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
  if (busy.value) error.value = 'Zadání se změnilo. Spusť návrh znovu.'
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
  error.value = ''
  emit('invalidate')
  busy.value = true
  emit('busy', true)
  const active = () => token === generation && scope === currentRepoId()
  let finished: Job | null = null
  const fail = (e: unknown) => {
    if (!active()) return
    error.value = e instanceof Error ? e.message : 'Návrh workflow selhal. Zkus to znovu.'
    if (finished) costs.value.push(finished.usage ?? null)
    stop()
  }
  const poll = async (id: string) => {
    if (!active()) return
    try {
      const job = await getApi<Job>(`/backlog/workflow-advice/${encodeURIComponent(id)}`, controller?.signal)
      if (!active()) return
      if (job.state === 'failed') {
        finished = job
        throw new Error(job.error || 'Návrh workflow selhal.')
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
</script>

<template>
  <div class="workflow-advice" data-test="workflow-advice">
    <button type="button" :disabled="disabled || busy" @click="start">
      <Spinner v-if="busy" />
      {{ busy ? 'Agent vybírá workflow…' : 'Navrhnout workflow' }}
    </button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-for="(cost, index) in costs" :key="index" data-test="workflow-advice-cost">
      Návrh {{ index + 1 }}: {{ costText(cost) }}
    </p>
    <div v-if="result" data-test="advice-result">
      <strong>{{ result.workflow_name }}</strong>
      · {{ result.decision === 'new' ? 'nové workflow' : 'existující workflow' }}
      <p>{{ result.reason }}</p>
      <p v-for="warning in result.warnings" :key="warning" class="faint">{{ warning }}</p>
      <ul><li v-for="(item, index) in result.outline" :key="index">{{ item.step || item.name || item.kind }}{{ item.agent ? ` · ${item.agent}` : '' }}{{ item.max ? ` (max ${item.max})` : '' }}</li></ul>
      <details v-if="result.workflow_yaml"><summary>YAML workflow</summary><pre>{{ result.workflow_yaml }}</pre></details>
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
