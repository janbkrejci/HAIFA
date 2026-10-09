<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { CheckFinding } from '@/lib/api'
import {
  addTask, commitBacklog, fetchBacklog, fetchRunCheck, fetchTask, flattenIssues, startRun,
  type AddTaskInput, type BacklogData, type EditTaskInput, type RunAction, type RunCheck,
  type RunStart, type TaskNode, type WriteError,
} from '@/lib/backlog'
import { useLive } from '@/lib/live'
import { taskHref, here } from '@/lib/router'
import TaskForm from '@/components/backlog/TaskForm.vue'
import RunDialog from '@/components/backlog/RunDialog.vue'

const props = defineProps<{ findings: CheckFinding[] }>()
const emit = defineEmits<{ close: [] }>()
const data = ref<BacklogData | null>(null)
const loading = ref(true)
const busy = ref(false)
const error = ref<WriteError | null>(null)
const task = ref<TaskNode | null>(null)
const check = ref<RunCheck | null>(null)
const result = ref<RunStart | null>(null)
const action = ref<RunAction | null>(null)
const waiting = ref(false)
let checkingPending = false

// A snapshot: subsequent checks must not change an already reviewed repair request.
const body = [
  'Vyřeš následující vybrané nálezy kontroly Factory. Po opravě spusť factory check a popiš výsledek každého vybraného nálezu.',
  'Respektuj povolené cesty a chráněné soubory. Nálezy tohoto počítače a knihovny řeš jen v rámci oprávnění běhu; pokud opravu nelze provést, uveď konkrétní překážku a postup pro operátora.',
  '',
  ...props.findings.map((f, i) => [
    `${i + 1}. ${f.code} (${f.scope}, ${f.severity})`,
    `   ${f.message}`,
    ...(f.fix ? [`   Doporučená oprava: ${f.fix}`] : []),
    ...(f.action ? [`   Akce: ${f.action}`] : []),
  ].join('\n')),
].join('\n')

async function load() {
  loading.value = true
  error.value = null
  try {
    if (task.value) check.value = await fetchRunCheck(task.value.id)
    else data.value = await fetchBacklog()
  } catch (e) { error.value = flattenIssues(e) }
  finally { loading.value = false }
}

async function create(input: AddTaskInput | EditTaskInput) {
  if (busy.value || task.value || !('step' in input)) return
  busy.value = true
  error.value = null
  try {
    const saved = await addTask(input)
    task.value = saved.task
    await load()
  } catch (e) { error.value = flattenIssues(e) }
  finally { busy.value = false }
}

async function commit() {
  if (busy.value || !task.value) return
  busy.value = true
  action.value = 'commit'
  error.value = null
  try {
    await commitBacklog()
    check.value = await fetchRunCheck(task.value.id)
  } catch (e) { error.value = flattenIssues(e) }
  finally { busy.value = false; action.value = null }
}

async function start(input: { note?: string; force: boolean }) {
  if (busy.value || waiting.value || result.value || !task.value || !check.value?.in_base) return
  busy.value = true
  action.value = input.force ? 'force' : 'start'
  error.value = null
  try {
    result.value = await startRun(task.value.id, input)
    waiting.value = result.value.pending && !result.value.run
    await claimPending()
  } catch (e) { error.value = flattenIssues(e) }
  finally { busy.value = false; if (!waiting.value) action.value = null }
}

async function claimPending() {
  if (!waiting.value || !task.value || !result.value || checkingPending) return
  checkingPending = true
  try {
    const detail = await fetchTask(task.value.id)
    const run = detail.runs[0] // this newly created task had no previous runs
    if (run) {
      result.value = { ...result.value, run, pending: false }
      waiting.value = false
      action.value = null
    }
  } catch (e) { error.value = flattenIssues(e) }
  finally { checkingPending = false }
}

useLive({ trace: () => { void claimPending() }, resync: () => { void claimPending() } })
onMounted(() => { void load() })
</script>

<template>
  <section class="repair" data-test="factory-repair">
    <h2>Vyřešit vybrané nálezy ({{ findings.length }})</h2>
    <p>Vytvoř opravný úkol, zvol workflow a povolené cesty, commitni backlog a spusť běh.</p>
    <template v-if="!task">
      <p v-if="loading">Načítám backlog…</p>
      <template v-else-if="data?.steps.length">
        <TaskForm mode="add" :steps="data.steps" :workflows="data.workflows"
          initial-title="Opravit vybrané nálezy Factory" :initial-body="body"
          :busy="busy" :pending="busy" :error="error" @submit="create" @cancel="emit('close')" />
      </template>
      <p v-else-if="data">Nejprve vytvoř krok v <a :href="here('backlog')">backlogu</a>.</p>
      <template v-if="!data">
        <p v-if="error" role="alert">{{ error.message }}</p>
        <button v-if="error" type="button" @click="load">Zkusit znovu</button>
      </template>
      <button v-if="!data?.steps.length" type="button" @click="emit('close')">Zavřít</button>
    </template>
    <template v-else>
      <p>Opravný úkol: <a :href="taskHref(task.id)">{{ task.id }}</a></p>
      <p v-if="!task.workflow || !task.writes.length">Před spuštěním nastav v úkolu workflow a povolené cesty.</p>
      <p>Commit backlogu zahrne všechny jeho necommitnuté změny.</p>
      <p v-if="check?.config && !check.config.clean">Nové nebo upravené workflow nejprve zveřejni na <a :href="here('factory') + '/config_commit'">stránce Factory</a>.</p>
      <RunDialog :check="check" :start-disabled="!check?.in_base || !task.workflow || !task.writes.length"
        :loading="loading" :busy="busy" :error="error" :result="result" :action="action" :waiting="waiting"
        @start="start" @commit="commit" @cancel="emit('close')" />
      <button v-if="error || waiting" type="button" :disabled="busy || loading" @click="waiting ? claimPending() : load()">Obnovit stav běhu</button>
    </template>
  </section>
</template>

<style scoped>
.repair { margin-top: 22px; padding: 16px; border: 1px solid var(--border); border-radius: 10px; }
h2 { margin-top: 0; font-size: 17px; }
button { color: var(--text); background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 6px 12px; cursor: pointer; }
</style>
