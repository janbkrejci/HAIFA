<script setup lang="ts">
// Prepare and start a task run (`factory task run [--note] [--force] [--harness] [--model]
// [--thinking] [--auto]`): what the run uses (workflow, writes, base, task text),
// the warnings first (uncommitted config D4, task not in base, unmet dependencies, a running
// run), a harness for this run only and auto continue.
import { computed, ref } from 'vue'
import {
  RUN_HARNESSES,
  THINKING_LEVELS,
  levelLabel,
  levelNoun,
  type RunAction,
  type RunCheck,
  type RunInput,
  type RunStart,
  type TaskNode,
  type WriteError,
} from '@/lib/backlog'
import { fetchFactoryRoster, type FactoryRosterAgent } from '@/lib/api'
import { errorText, shortSha } from '@/lib/format'
import { useLevels } from '@/lib/names'
import { currentRepoId, here, runHref } from '@/lib/router'
import type { SelectOption } from '@/lib/select'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'

const props = defineProps<{
  check: RunCheck | null
  /** The task to run (summary fallback when the check lacks the effective values). */
  task?: TaskNode | null
  /** The task text (`body` of the task detail). */
  body?: string
  loading: boolean
  busy: boolean
  error: WriteError | null
  result: RunStart | null
  /** The button whose action is running (spinner). */
  action?: RunAction | null
  /** Start answered `pending`: the run is still starting. */
  waiting?: boolean
  startDisabled?: boolean
}>()

const emit = defineEmits<{
  start: [input: RunInput & { force: boolean }]
  cancel: []
  commit: []
}>()

const note = ref('')
const harness = ref('')
const model = ref('')
const thinking = ref('')
const auto = ref(false)
const level = useLevels()
const taskNoun = computed(() => levelNoun(level.task.value))
const taskLabel = computed(() => levelLabel(level.task.value))

const unmet = computed(() => (Array.isArray(props.check?.unmet) ? props.check.unmet : []))
const config = computed(() => props.check?.config ?? null)
const dirtyConfig = computed(() => config.value !== null && !config.value.clean)
const running = computed(() => props.check?.running ?? null)
const launcherBusy = computed(() => props.check?.launcher_busy === true)
const notInBase = computed(() => !!props.check && props.check.in_base === false)
const showForce = computed(
  () => unmet.value.length > 0 || props.error?.code === 'unmet_dependencies',
)
const blocked = computed(
  () =>
    props.busy ||
    props.startDisabled ||
    props.waiting ||
    props.result !== null ||
    props.loading ||
    !props.check ||
    notInBase.value ||
    running.value !== null ||
    launcherBusy.value,
)

// ── summary: what the run uses ───────────────────────────────────────────────
const workflow = computed(() =>
  props.check && 'workflow' in props.check ? (props.check.workflow ?? null) : (props.task?.workflow ?? null),
)
const writes = computed(() => {
  const own = props.check && Array.isArray(props.check.writes) ? props.check.writes : props.task?.writes
  return Array.isArray(own) ? own : []
})
const baseSha = computed(() => shortSha(config.value?.commit ?? ''))
const configCommitHref = computed(() => {
  const id = currentRepoId()
  return id ? `${here('factory')}/config_commit` : here('factory')
})

// ── harness for this run ─────────────────────────────────────────────────────
const ROSTER = 'podle rosteru'
const harnessOptions: SelectOption[] = [
  { value: '', label: ROSTER },
  ...RUN_HARNESSES.map((h) => ({ value: h, label: h })),
]
const thinkingOptions: SelectOption[] = [
  { value: '', label: ROSTER },
  ...THINKING_LEVELS.map((t) => ({ value: t, label: t })),
]
const roster = ref<FactoryRosterAgent[] | null>(null)
const rosterError = ref('')
const rosterLoading = ref(false)

async function loadRoster() {
  const id = currentRepoId()
  if (roster.value !== null || rosterLoading.value || !id) return
  rosterLoading.value = true
  rosterError.value = ''
  try {
    const data = await fetchFactoryRoster(id)
    roster.value = Array.isArray(data?.agents) ? data.agents : []
  } catch (e) {
    rosterError.value = errorText(e)
  } finally {
    rosterLoading.value = false
  }
}

function onHarnessToggle(event: Event) {
  if ((event.target as HTMLDetailsElement).open) void loadRoster()
}

function start(force: boolean) {
  const input: RunInput & { force: boolean } = { force }
  const text = note.value.trim()
  if (text) input.note = text
  if (harness.value) input.harness = harness.value
  if (model.value.trim()) input.model = model.value.trim()
  if (thinking.value) input.thinking = thinking.value
  if (auto.value) input.auto = true
  emit('start', input)
}
</script>

<template>
  <section class="run-dialog" data-test="run-dialog">
    <h3>Spustit {{ taskNoun }}</h3>
    <p v-if="loading" class="faint" data-test="run-loading">Kontroluji…</p>
    <template v-else-if="check">
      <dl class="summary" data-test="run-summary">
        <dt>Workflow</dt>
        <dd data-test="summary-workflow">{{ workflow ?? 'bez workflow' }}</dd>
        <dt>Zápisy</dt>
        <dd class="mono" data-test="summary-writes">{{ writes.join(', ') || '—' }}</dd>
        <dt>Base</dt>
        <dd data-test="summary-base">
          <code>{{ check.base }}</code><template v-if="baseSha"> (<code>{{ baseSha }}</code>)</template>
        </dd>
      </dl>
      <details v-if="body !== undefined" class="body" data-test="summary-body">
        <summary>Zadání</summary>
        <MarkdownView :source="body ?? ''" empty="Bez zadání." />
      </details>

      <div v-if="dirtyConfig && config" class="warning" data-test="config-warning">
        <p>
          Konfigurace <code>.factory/</code> má necommitnuté změny, běh použije verzi z
          {{ config.base }} ({{ shortSha(config.commit) }}).
        </p>
        <ul>
          <li v-for="c in config.changes" :key="c.path" class="mono">{{ c.status }} {{ c.path }}</li>
        </ul>
        <a :href="configCommitHref" class="button-link" data-test="config-commit-link">Commitnout konfiguraci</a>
      </div>
      <div v-if="notInBase" class="warning" data-test="not-in-base">
        <p>{{ taskLabel }} není commitnutý v base ({{ check.base }}), běh ho nenajde. Nejdřív commitni backlog.</p>
        <button
          type="button"
          data-test="commit-backlog"
          :disabled="busy || waiting"
          :aria-busy="action === 'commit' || undefined"
          @click="emit('commit')"
        >
          <Spinner v-if="action === 'commit'" />
          Commitnout backlog do base
        </button>
      </div>
      <div v-if="unmet.length" class="warning" data-test="unmet-warning">
        <p>Nesplněné závislosti v base:</p>
        <ul>
          <li v-for="u in unmet" :key="u.id" :data-unmet="u.id">
            <span class="mono">{{ u.id }}</span> — {{ u.reason }}
          </li>
        </ul>
      </div>
      <div v-if="running" class="info" data-test="run-running">
        {{ taskLabel }} už běží:
        <a :href="runHref(running.run_id)" class="mono">{{ running.run_id }}</a>
      </div>
      <div v-else-if="launcherBusy" class="info" data-test="launcher-busy">
        Z dashboardu už běží jiný běh, počkej na jeho konec.
        <a :href="here('runs')" data-test="launcher-busy-link">Běžící běhy</a>
      </div>
    </template>

    <details class="harness" data-test="run-harness" @toggle="onHarnessToggle">
      <summary>Harness pro tento běh</summary>
      <p class="faint">Prázdné = podle tasku, projektu a nastavení tohoto počítače. Přepíše harness všech agentů jen pro tento běh; přepisy na krocích workflow platí dál.</p>
      <div class="harness-fields">
        <label>
          Harness
          <SelectMenu v-model="harness" data-test="run-harness-name" label="Harness" :options="harnessOptions" :disabled="busy" />
        </label>
        <label>
          Model
          <input v-model="model" data-test="run-model" type="text" :placeholder="ROSTER" :disabled="busy" />
        </label>
        <label>
          Přemýšlení
          <SelectMenu v-model="thinking" data-test="run-thinking" label="Přemýšlení" :options="thinkingOptions" :disabled="busy" />
        </label>
      </div>
      <p v-if="rosterLoading" class="faint" data-test="roster-loading">Načítám roster…</p>
      <p v-else-if="rosterError" class="faint" data-test="roster-error">Roster nejde načíst: {{ rosterError }}</p>
      <table v-else-if="roster" class="roster" data-test="roster">
        <thead>
          <tr><th>Agent</th><th>Harness</th><th>Model</th><th>Přemýšlení</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in roster" :key="a.name" :data-agent="a.name">
            <td class="mono">{{ a.name }}</td>
            <td>{{ a.harness ?? 'výchozí' }}</td>
            <td class="mono">{{ a.model ?? 'výchozí' }}</td>
            <td>{{ a.thinking ?? 'výchozí' }}</td>
          </tr>
        </tbody>
      </table>
    </details>

    <label class="check">
      <input v-model="auto" type="checkbox" class="switch" role="switch" data-test="run-auto" :disabled="busy" />
      Po úspěchu pokračovat dalšími tasky (auto continue)
    </label>
    <p class="faint hint">Pořadí a vyloučení tasků řídí kanban (sloupce Připraveno a Odloženo).</p>

    <label class="note">
      <span>Poznámka (volitelná)</span>
      <textarea v-model="note" data-test="run-note" rows="3" :disabled="busy" />
    </label>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />

    <p v-if="result" class="success" data-test="run-result">
      <template v-if="result.run">
        Běh <span class="mono">{{ result.run.run_id }}</span> spuštěn.
        <a :href="runHref(result.run.run_id)" class="button-link" data-test="run-open">Otevřít běh</a>
      </template>
      <template v-else>Běh se spouští…</template>
    </p>

    <div class="actions">
      <button
        type="button"
        class="primary"
        data-test="run-start"
        :disabled="blocked || unmet.length > 0"
        :aria-busy="action === 'start' || undefined"
        @click="start(false)"
      >
        <Spinner v-if="action === 'start'" />
        Spustit
      </button>
      <button
        v-if="showForce"
        type="button"
        data-test="run-force"
        :disabled="blocked"
        :aria-busy="action === 'force' || undefined"
        @click="start(true)"
      >
        <Spinner v-if="action === 'force'" />
        Spustit přesto (ignorovat nesplněné závislosti)
      </button>
      <button type="button" data-test="run-cancel" :disabled="busy" @click="emit('cancel')">
        Zavřít
      </button>
    </div>
  </section>
</template>

<style scoped>
.run-dialog {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  border: 1px solid rgba(108, 182, 255, 0.45);
  border-radius: 10px;
  background: var(--panel-2);
}

h3 {
  margin: 0;
  font-size: 16px;
  color: var(--dim);
}

p {
  margin: 0;
}

ul {
  margin: 4px 0 0;
  padding-left: 20px;
}

.mono,
code {
  font-family: var(--mono);
  font-size: 14px;
}

.summary {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 16px;
  margin: 0;
}

.summary dt {
  color: var(--faint);
}

.summary dd {
  margin: 0;
}

summary {
  cursor: pointer;
  color: var(--dim);
}

.harness-fields {
  display: grid;
  grid-template-columns: repeat(3, minmax(140px, 1fr));
  gap: 10px;
  margin-top: 8px;
}

.harness-fields label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--faint);
}

.harness > p {
  margin-top: 6px;
  font-size: 13px;
}

.roster {
  margin-top: 8px;
  border-collapse: collapse;
}

.roster th,
.roster td {
  padding: 3px 10px 3px 0;
  text-align: left;
  font-size: 13px;
}

.roster th {
  color: var(--faint);
  font-weight: 500;
}

.warning {
  padding: 8px 12px;
  border: 1px solid rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  background: rgba(232, 182, 74, 0.08);
  color: var(--amber);
}

.warning button,
.warning .button-link {
  margin-top: 6px;
}

.warning li {
  color: var(--text);
}

.info {
  padding: 8px 12px;
  border: 1px solid rgba(108, 182, 255, 0.45);
  border-radius: 8px;
  background: rgba(108, 182, 255, 0.08);
  color: var(--blue);
}

.success {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--green);
}

.check {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text);
}

.hint {
  font-size: 13px;
}

.note {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--faint);
}

textarea,
input[type='text'] {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

.actions {
  display: flex;
  gap: 8px;
}

button,
.button-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}

button.primary {
  border-color: rgba(108, 182, 255, 0.6);
  color: var(--blue);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
