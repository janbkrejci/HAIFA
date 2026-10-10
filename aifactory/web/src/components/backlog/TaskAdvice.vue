<script setup lang="ts">
import { errorText } from '../../lib/format'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getApi, postApi } from '@/lib/api'
import { currentRepoId } from '@/lib/router'
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
interface AdvisorHarness { name: string; default_model: string; models: string[] }
interface AdvisorOptions { default: { harness: string; model: string } | null; harnesses: AdvisorHarness[] }
const choices = ref<AdvisorOptions | null>(null)
const harness = ref('')
const model = ref('')
const busy = ref(false)
const error = ref('')
const result = ref<TaskProposal | null>(null)
const stale = ref(false)
const costs = ref<(TaskProposal['usage'])[]>([])
/** The harness options were loaded (no default and no harness then means nothing can run). */
const loaded = ref(false)
const harnessOptions = computed(() => {
  const fallback = choices.value?.default
  return [
    { value: '', label: fallback ? `Systémový default (${fallback.harness} · ${fallback.model || 'model harnessu'})` : 'Systémový default' },
    ...(choices.value?.harnesses ?? []).map(h => ({ value: h.name, label: h.name })),
  ]
})
const selectedHarness = computed(() => choices.value?.harnesses.find(h => h.name === harness.value))
const modelOptions = computed(() => [
  { value: '', label: `Default harnessu (${selectedHarness.value?.default_model || 'nenastaven'})` },
  ...(selectedHarness.value?.models ?? []).map(m => ({ value: m, label: m })),
])
const empty = computed(() => loaded.value && !choices.value?.default && !choices.value?.harnesses.length)
const canStart = computed(() => loaded.value && (!!choices.value?.default || !!harness.value))
/** Restoring a stored choice must not reset its model. */
let restoring = false
watch(harness, () => { if (!restoring) model.value = '' })
let scope = currentRepoId()
const storageKey = () => `haifa.task-advice.choice.${scope || 'default'}`
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
  choices.value = null
  loaded.value = false
  restoring = true
  harness.value = ''
  model.value = ''
  restoring = false
  void loadOptions()
}
window.addEventListener('hashchange', scopeChanged)
onBeforeUnmount(() => { stop(); window.removeEventListener('hashchange', scopeChanged) })
async function loadOptions() {
  const requestedScope = scope
  try {
    const data = await getApi<AdvisorOptions>('/backlog/task-advice/options')
    if (requestedScope !== currentRepoId()) return
    choices.value = { default: data.default ?? null, harnesses: data.harnesses ?? [] }
    loaded.value = true
    let saved: { harness?: unknown; model?: unknown } = {}
    try { saved = JSON.parse(localStorage.getItem(storageKey()) ?? '{}') ?? {} } catch { /* storage is optional */ }
    const offered = choices.value.harnesses.find(h => h.name === saved.harness)
    const savedModel = typeof saved.model === 'string' ? saved.model : ''
    const valid = offered && (savedModel === '' || offered.models.includes(savedModel))
    restoring = true
    harness.value = valid ? offered.name : ''
    model.value = valid ? savedModel : ''
    await nextTick()
    restoring = false
  } catch (e) { if (requestedScope === currentRepoId()) error.value = errorText(e) }
}
onMounted(loadOptions)
async function start() {
  if (busy.value || props.disabled || !canStart.value) return
  stop()
  const token = generation
  const active = () => token === generation && scope === currentRepoId()
  stale.value = false
  result.value = null
  error.value = ''
  busy.value = true
  emit('busy', true)
  controller = new AbortController()
  try { localStorage.setItem(storageKey(), JSON.stringify({ harness: harness.value, model: model.value })) } catch { /* storage is optional */ }
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
      ...(props.taskId ? { task_id: props.taskId } : {}), draft: props.draft,
      ...(harness.value ? { harness: harness.value } : {}), ...(model.value ? { model: model.value } : {}),
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
    <p v-if="empty" class="no-agents" data-test="advice-no-agents">
      Návrh potřebuje povolený harness. Nastav harnessy počítače v nastavení harnessů.
    </p>
    <template v-else>
      <label>Harness pro návrh
        <SelectMenu v-model="harness" data-test="advice-harness" label="Harness" :options="harnessOptions" :disabled="busy" />
      </label>
      <label v-if="harness">Model pro návrh
        <SelectMenu v-model="model" data-test="advice-model" label="Model" :options="modelOptions" :disabled="busy" />
      </label>
    </template>
    <button type="button" data-test="task-advice-start" :disabled="disabled || busy || !canStart" @click="start">
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
