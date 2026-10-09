<script setup lang="ts">
import { errorText } from '../../lib/format'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getApi, postApi } from '@/lib/api'
import { currentRepoId, here } from '@/lib/router'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'

export interface TaskProposal {
  title: string
  body: string
  writes: string[] | null
  depends_on: string[]
  related: string[]
  workflow: string | null
  parameters?: Record<string, unknown>
  reason: string
  usage?: { tokens: number; cost_usd: number | null } | null
}
interface Job {
  job_id: string
  state: string
  recommendation: TaskProposal | null
  error: string | null
  usage?: TaskProposal['usage']
}
const props = defineProps<{ draft: Record<string, unknown>; taskId?: string; disabled?: boolean }>()
const emit = defineEmits<{ result: [proposal: TaskProposal]; busy: [value: boolean] }>()
const choices = ref<{ name: string; provider: string; model: string }[]>([])
const agent = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<TaskProposal | null>(null)
const stale = ref(false)
const costs = ref<(TaskProposal['usage'])[]>([])
/** The agent options were loaded (an empty list then means the roster has no agent). */
const loaded = ref(false)
const options = computed(() => choices.value.map(a => ({ value: a.name, label: `${a.provider} · ${a.model} (${a.name})` })))
let scope = currentRepoId()
const storageKey = () => `haifa.task-advice.agent.${scope || 'default'}`
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
function stop() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  busy.value = false
  emit('busy', false)
}
watch(() => JSON.stringify([props.taskId, props.draft]), () => {
  stale.value = true
})
function scopeChanged() {
  if (scope === currentRepoId()) return
  stop()
  scope = currentRepoId()
  result.value = null
  costs.value = []
  choices.value = []
  loaded.value = false
  agent.value = ''
  void loadOptions()
}
window.addEventListener('hashchange', scopeChanged)
onBeforeUnmount(() => { stop(); window.removeEventListener('hashchange', scopeChanged) })
async function loadOptions() {
  const requestedScope = scope
  try {
    const data = await getApi<{ agents: typeof choices.value }>('/backlog/task-advice/options')
    if (requestedScope !== currentRepoId()) return
    choices.value = data.agents ?? []
    loaded.value = true
    let saved = ''
    try { saved = localStorage.getItem(storageKey()) ?? '' } catch { /* storage is optional */ }
    agent.value = choices.value.find(a => a.name === saved)?.name ?? choices.value[0]?.name ?? ''
  } catch (e) { if (requestedScope === currentRepoId()) error.value = errorText(e) }
}
onMounted(loadOptions)
async function start() {
  if (busy.value || props.disabled || !agent.value) return
  stop()
  const token = generation
  const active = () => token === generation && scope === currentRepoId()
  stale.value = false
  result.value = null
  error.value = ''
  busy.value = true
  emit('busy', true)
  controller = new AbortController()
  try { localStorage.setItem(storageKey(), agent.value) } catch { /* storage is optional */ }
  async function poll(id: string) {
    if (!active()) return
    try {
      const job = await getApi<Job>(`/backlog/task-advice/${encodeURIComponent(id)}`, controller?.signal)
      if (!active()) return
      if (job.state === 'failed') {
        costs.value.push(job.usage)
        error.value = job.error || 'Návrh parametrů selhal.'
        stop()
        return
      }
      if (job.state === 'succeeded' && job.recommendation) {
        result.value = job.recommendation
        costs.value.push(job.recommendation.usage)
        stop()
      } else timer = setTimeout(() => void poll(id), 800)
    } catch (e) { fail(e) }
  }
  function fail(e: unknown) {
    if (!active()) return
    error.value = errorText(e)
    costs.value.push(null)
    stop()
  }
  try {
    const job = await postApi<Job>('/backlog/task-advice', {
      ...(props.taskId ? { task_id: props.taskId } : {}), draft: props.draft, agent: agent.value,
    }, controller.signal)
    if (active()) await poll(job.job_id)
  } catch (e) { fail(e) }
}
function apply() {
  if (!result.value || stale.value) return
  emit('result', result.value)
  result.value = null
}
</script>

<template>
  <div class="task-advice" data-test="task-advice">
    <p v-if="loaded && !choices.length" class="no-agents" data-test="advice-no-agents">
      Návrh potřebuje agenta z rosteru repa, roster je prázdný. Agenty nastav v záložce
      <a :href="here('factory')">Factory</a>.
    </p>
    <label v-else>Provider a model pro návrh
      <SelectMenu v-model="agent" data-test="advice-agent" label="Provider a model" :options="options" :disabled="busy" />
    </label>
    <button type="button" data-test="task-advice-start" :disabled="disabled || busy || !agent" @click="start">
      <Spinner v-if="busy" />{{ busy ? 'Agent navrhuje parametry…' : 'Navrhnout parametry tasku' }}
    </button>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-for="(cost, index) in costs" :key="index" data-test="task-advice-cost">
      Návrh {{ index + 1 }}: {{ cost ? `${cost.cost_usd == null ? 'Provider cenu nevykázal' : `$${cost.cost_usd.toFixed(4)} USD`} · ${cost.tokens} tokenů (vykázané providerem)` : 'Provider náklady nevykázal.' }}
    </p>
    <div v-if="result" data-test="task-advice-result">
      <p>{{ result.reason }}</p>
      <strong>{{ result.title }}</strong>
      <pre>{{ result.body }}</pre>
      <p>Writes: {{ result.writes?.join(', ') ?? 'zděděno' }}</p>
      <p>Závisí na: {{ result.depends_on.join(', ') || 'žádné' }}</p>
      <p>Související: {{ result.related.join(', ') || 'žádné' }}</p>
      <p v-for="(value, key) in result.parameters" :key="key">{{ key }}: {{ value ?? 'zděděno' }}</p>
      <p>Workflow: {{ result.workflow ?? 'zděděno' }}</p>
      <p v-if="stale">Zadání se změnilo. Spusť návrh znovu.</p>
      <button type="button" data-test="task-advice-apply" :disabled="disabled || stale" @click="apply">Použít návrh do formuláře</button>
    </div>
  </div>
</template>

<style scoped>
.task-advice { display: flex; flex-direction: column; gap: 10px; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
button { align-self: flex-start; padding: 6px 14px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel); color: var(--text); cursor: pointer; }
button:disabled { opacity: 0.5; cursor: default; }
[role='alert'] { color: var(--red); }
.no-agents { margin: 0; color: var(--amber); }
</style>
