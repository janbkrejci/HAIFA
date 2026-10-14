<script lang="ts">
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
export interface Advisor { harness?: string; model?: string; thinking?: string }
</script>

<script setup lang="ts">
// "Vylepšit agentem": the task advice runs with the harness, model and thinking level
// the task inherits (the same agent it would run with); the result goes straight into the form.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Wand2, X } from 'lucide-vue-next'
import { errorText } from '@/lib/format'
import { getApi, postApi } from '@/lib/api'
import { currentRepoId } from '@/lib/router'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

interface Job {
  job_id: string
  state: string
  recommendation: TaskProposal | null
  error: string | null
  usage?: TaskProposal['usage']
  advisor?: Advisor | null
}
const props = defineProps<{
  draft: Record<string, unknown>
  taskId?: string
  disabled?: boolean
  /** Why the improvement cannot run (tooltip); '' or absent when it can. */
  blocker?: string
  /** Start once right after mounting (the detail's button opened the form). */
  autostart?: boolean
}>()
const emit = defineEmits<{ result: [proposal: TaskProposal]; busy: [value: boolean] }>()

const busy = ref(false)
const error = ref('')
const note = ref<{ reason: string; advisor: Advisor | null; usage: TaskProposal['usage'] } | null>(null)
const blocked = computed(() => !!props.disabled || !!props.blocker)

let scope = currentRepoId()
let generation = 0
let timer: ReturnType<typeof setTimeout> | undefined
let controller: AbortController | undefined
function stop() {
  generation++
  clearTimeout(timer)
  controller?.abort()
  if (busy.value) emit('busy', false)
  busy.value = false
}
watch(() => JSON.stringify([props.taskId, props.draft]), () => {
  if (!busy.value) return
  stop()
  error.value = 'Zadání se změnilo. Spusť vylepšení znovu.'
})
function scopeChanged() {
  if (scope === currentRepoId()) return
  stop()
  scope = currentRepoId()
  note.value = null
  error.value = ''
}
window.addEventListener('hashchange', scopeChanged)
onBeforeUnmount(() => { stop(); window.removeEventListener('hashchange', scopeChanged) })

function advisorText(advisor: Advisor | null): string {
  if (!advisor?.harness) return ''
  return [advisor.harness, advisor.model, advisor.thinking].filter(Boolean).join(' · ')
}
function costText(usage: TaskProposal['usage']): string {
  if (!usage) return 'Provider náklady nevykázal.'
  const cost = usage.cost_usd == null ? 'Provider cenu nevykázal' : `$${usage.cost_usd.toFixed(4)} USD`
  return `${cost} · ${usage.tokens} tokenů (vykázané providerem)`
}

async function start() {
  if (busy.value || blocked.value) return
  stop()
  const token = generation
  const active = () => token === generation && scope === currentRepoId()
  error.value = ''
  note.value = null
  busy.value = true
  emit('busy', true)
  controller = new AbortController()
  let advisor: Advisor | null = null
  function fail(e: unknown) {
    if (!active()) return
    error.value = errorText(e)
    stop()
  }
  async function poll(id: string) {
    if (!active()) return
    try {
      const job = await getApi<Job>(`/backlog/task-advice/${encodeURIComponent(id)}`, controller?.signal)
      if (!active()) return
      advisor = job.advisor ?? advisor
      if (job.state === 'failed') {
        error.value = job.error || 'Vylepšení selhalo.'
        stop()
        return
      }
      if (job.state === 'succeeded' && job.recommendation) {
        const proposal = job.recommendation
        stop()
        note.value = { reason: proposal.reason, advisor, usage: proposal.usage ?? job.usage ?? null }
        emit('result', proposal)
      } else timer = setTimeout(() => void poll(id), 800)
    } catch (e) { fail(e) }
  }
  try {
    const job = await postApi<Job>('/backlog/task-advice', {
      ...(props.taskId ? { task_id: props.taskId } : {}), draft: props.draft,
    }, controller.signal)
    if (!active()) return
    advisor = job.advisor ?? null
    await poll(job.job_id)
  } catch (e) { fail(e) }
}
onMounted(() => { if (props.autostart) void start() })
defineExpose({ start })
</script>

<template>
  <div class="improve">
    <Tooltip :text="busy ? '' : (blocker ?? '')">
      <button
        type="button"
        class="btn-improve"
        data-test="improve"
        :disabled="busy || blocked"
        :aria-busy="busy || undefined"
        @click="start"
      >
        <Spinner v-if="busy" />
        <Wand2 v-else :size="18" />
        {{ busy ? 'Agent vylepšuje…' : 'Vylepšit agentem' }}
      </button>
    </Tooltip>
    <p v-if="error" role="alert" data-test="improve-error">{{ error }}</p>
    <div v-if="note" class="note" data-test="improve-note">
      <button type="button" class="close" aria-label="Zavřít" data-test="improve-note-close" @click="note = null"><X :size="14" /></button>
      <p>{{ note.reason }}</p>
      <p class="faint" data-test="improve-meta">
        <span v-if="advisorText(note.advisor)" data-test="improve-advisor">{{ advisorText(note.advisor) }} · </span>
        <span data-test="improve-cost">{{ costText(note.usage) }}</span>
      </p>
    </div>
  </div>
</template>

<style scoped>
.improve {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
  min-width: 0;
}
p {
  margin: 0;
}
[role='alert'] {
  color: var(--red);
  max-width: 420px;
  text-align: right;
}
.note {
  position: relative;
  max-width: 420px;
  padding: 8px 28px 8px 10px;
  border: 1px solid color-mix(in srgb, var(--green) 45%, transparent);
  border-radius: 8px;
  background: color-mix(in srgb, var(--green) 8%, var(--panel));
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.faint {
  color: var(--faint);
}
button.close {
  position: absolute;
  top: 4px;
  right: 4px;
  display: inline-flex;
  padding: 2px;
  border: 0;
  background: transparent;
  color: var(--faint);
  cursor: pointer;
}
</style>
