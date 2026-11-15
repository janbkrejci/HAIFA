<script setup lang="ts">
import { t } from '@/lib/i18n'
import { backlogError } from '@/lib/backlogMessages'
import { flattenIssues } from '@/lib/backlog'
// Prepare and start a task run (`factory task run [--note] [--force] [--harness] [--model]
// [--thinking]`): what the run uses (workflow, writes, base, task text),
// the warnings first (uncommitted config D4, task not in base, unmet dependencies, a running
// run) and a harness for this run only. Continuation uses the local repository policy.
import { computed, ref } from 'vue'
import {
  RUN_HARNESSES,
  THINKING_LEVELS,
  levelLabel,
  levelNoun,
  unmetLine,
  type RunAction,
  type RunCheck,
  type RunInput,
  type RunStart,
  type TaskNode,
  type WriteError,
} from '@/lib/backlog'
import { fetchFactoryRoster, type FactoryRosterAgent } from '@/lib/api'
import { askDiscard, useUnsavedGuard } from '@/lib/leaveGuard'
import { shortSha } from '@/lib/format'
import { useLevels } from '@/lib/names'
import { currentRepoId, here, OVERVIEW_HREF, runHref } from '@/lib/router'
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
const dirty = computed(() => !props.result && !!(note.value.trim() || harness.value || model.value.trim() || thinking.value))
useUnsavedGuard(() => dirty.value)
async function cancel() {
  if (dirty.value && !(await askDiscard())) return
  note.value = harness.value = model.value = thinking.value = ''
  emit('cancel')
}
const level = useLevels()
const taskNoun = computed(() => levelNoun(level.task.value))
const taskLabel = computed(() => levelLabel(level.task.value))

const unmet = computed(() => (Array.isArray(props.check?.unmet) ? props.check.unmet : []))
/** The dependencies wait only in open PRs: the run starts from their branch (stacked PRs). */
const stack = computed(() => props.check?.stack ?? null)
/** Unmet dependencies that stop a normal start (none when the run stacks on their PRs). */
const blocking = computed(() => (stack.value ? [] : unmet.value))
const config = computed(() => props.check?.config ?? null)
const dirtyConfig = computed(() => config.value !== null && !config.value.clean)
const running = computed(() => props.check?.running ?? null)
const launcherBusy = computed(() => props.check?.launcher_busy === true)
const notInBase = computed(() => !!props.check && props.check.in_base === false)
const blocked = computed(
  () =>
    props.error?.code === 'unmet_dependencies' ||
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
const ROSTER = computed(() => t('backlog.fromRoster'))
const harnessOptions = computed<SelectOption[]>(() => [
  { value: '', label: ROSTER.value },
  ...RUN_HARNESSES.map((h) => ({ value: h, label: h })),
])
const thinkingOptions = computed<SelectOption[]>(() => [
  { value: '', label: ROSTER.value },
  ...THINKING_LEVELS.map((t) => ({ value: t, label: t })),
])
const roster = ref<FactoryRosterAgent[] | null>(null)
const rosterError = ref<(() => string) | null>(null)
const rosterLoading = ref(false)

async function loadRoster() {
  const id = currentRepoId()
  if (roster.value !== null || rosterLoading.value || !id) return
  rosterLoading.value = true
  rosterError.value = null
  try {
    const data = await fetchFactoryRoster(id)
    roster.value = Array.isArray(data?.agents) ? data.agents : []
  } catch (e) {
    rosterError.value = () => backlogError(flattenIssues(e))
  } finally {
    rosterLoading.value = false
  }
}

function onHarnessToggle(event: Event) {
  if ((event.target as HTMLDetailsElement).open) void loadRoster()
}

function start(force: boolean) {
  if (blocked.value || blocking.value.length) return
  const input: RunInput & { force: boolean } = { force }
  const text = note.value.trim()
  if (text) input.note = text
  if (harness.value) input.harness = harness.value
  if (model.value.trim()) input.model = model.value.trim()
  if (thinking.value) input.thinking = thinking.value
  emit('start', input)
}
</script>

<template>
  <section class="run-dialog" data-test="run-dialog">
    <h3>{{ t('backlog.spustit') }} {{ taskNoun }}</h3>
    <p v-if="loading" class="faint" data-test="run-loading">{{ t('backlog.kontroluji') }}</p>
    <template v-else-if="check">
      <dl class="summary" data-test="run-summary">
        <dt>{{ t('backlog.workflowLabel') }}</dt>
        <dd data-test="summary-workflow">{{ workflow ?? t('backlog.bez_workflow') }}</dd>
        <dt>{{ t('backlog.zapisy') }}</dt>
        <dd class="mono" data-test="summary-writes">{{ writes.join(', ') || '—' }}</dd>
        <dt>{{ t('backlog.base') }}</dt>
        <dd data-test="summary-base">
          <code>{{ check.base }}</code><template v-if="baseSha"> (<code>{{ baseSha }}</code>)</template>
        </dd>
      </dl>
      <details v-if="body !== undefined" class="body" data-test="summary-body">
        <summary>{{ t('backlog.zadani') }}</summary>
        <MarkdownView :source="body ?? ''" :empty="t('backlog.bez_zadani')" />
      </details>

      <div v-if="dirtyConfig && config" class="warning" data-test="config-warning">
        <p>
          {{ t('backlog.konfigurace') }} <code>{{ t('backlog.factory') }}</code> {{ t('backlog.ma_necommitnute_zmeny_beh_pouzije_verzi_z') }}
          {{ config.base }} ({{ shortSha(config.commit) }}).
        </p>
        <ul>
          <li v-for="c in config.changes" :key="c.path" class="mono">{{ c.status }} {{ c.path }}</li>
        </ul>
        <a :href="configCommitHref" class="button-link" data-test="config-commit-link">{{ t('backlog.commitnout_konfiguraci') }}</a>
      </div>
      <div v-if="notInBase" class="warning" data-test="not-in-base">
        <p>{{ taskLabel }} {{ t('backlog.neni_commitnuty_v_base') }}{{ check.base }}{{ t('backlog.beh_ho_nenajde_nejdriv_commitni_backlog') }}</p>
        <button
          type="button"
          data-test="commit-backlog"
          :disabled="busy || waiting"
          :aria-busy="action === 'commit' || undefined"
          @click="emit('commit')"
        >
          <Spinner v-if="action === 'commit'" />
          {{ t('backlog.commitnout_backlog_do_base') }}
        </button>
      </div>
      <div v-if="stack" class="info" data-test="run-stacked">
        {{ t('backlog.zavislosti_cekaji_v_otevrenych_pr_beh_navaze_na_vetev') }}
        <span class="mono">{{ stack.branch }}</span>:
        <ul>
          <li v-for="pr in stack.prs" :key="pr.task_id" :data-stack="pr.task_id">
            <span class="mono">{{ pr.task_id }}</span> —
            <a :href="pr.url" target="_blank" rel="noopener">{{ pr.url }}</a>
          </li>
        </ul>
        {{ t('backlog.pr_tohoto_tasku_se_mergne_az_po_nich') }}
      </div>
      <div v-else-if="unmet.length" class="warning" data-test="unmet-warning">
        <p>{{ t('backlog.nesplnene_zavislosti_v_base') }}</p>
        <ul>
          <li v-for="u in unmet" :key="u.id" :data-unmet="u.id">
            {{ unmetLine(u) }}
          </li>
        </ul>
      </div>
      <div v-if="running" class="info" data-test="run-running">
        {{ taskLabel }} {{ t('backlog.uz_bezi') }}
        <a :href="runHref(running.run_id)" class="mono">{{ running.run_id }}</a>
      </div>
      <div v-else-if="launcherBusy" class="info" data-test="launcher-busy">
        {{ t('backlog.z_dashboardu_uz_bezi_jiny_beh_pockej_na_jeho_konec') }}
        <a :href="here('runs')" data-test="launcher-busy-link">{{ t('backlog.bezici_behy') }}</a>
      </div>
    </template>

    <details class="harness" data-test="run-harness" @toggle="onHarnessToggle">
      <summary>{{ t('backlog.harness_pro_tento_beh') }}</summary>
      <p class="faint">{{ t('backlog.prazdne_podle_tasku_projektu_a_nastaveni_tohoto_pocitace_prepise_harness_vs') }}</p>
      <div class="harness-fields">
        <label>
          {{ t('backlog.harness') }}
          <SelectMenu v-model="harness" data-test="run-harness-name" :label="t('backlog.harness')" :options="harnessOptions" :disabled="busy" />
        </label>
        <label>
          {{ t('backlog.model') }}
          <input v-model="model" data-test="run-model" type="text" :placeholder="ROSTER" :disabled="busy" />
        </label>
        <label>
          {{ t('backlog.premysleni') }}
          <SelectMenu v-model="thinking" data-test="run-thinking" :label="t('backlog.premysleni')" :options="thinkingOptions" :disabled="busy" />
        </label>
      </div>
      <p v-if="rosterLoading" class="faint" data-test="roster-loading">{{ t('backlog.nacitam_roster') }}</p>
      <p v-else-if="rosterError" class="faint" data-test="roster-error">{{ t('backlog.roster_nejde_nacist') }} {{ rosterError() }}</p>
      <table v-else-if="roster" class="roster" data-test="roster">
        <thead>
          <tr><th>{{ t('backlog.agent') }}</th><th>{{ t('backlog.harness') }}</th><th>{{ t('backlog.model') }}</th><th>{{ t('backlog.premysleni') }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="a in roster" :key="a.name" :data-agent="a.name">
            <td class="mono">{{ a.name }}</td>
            <td>{{ a.harness ?? t('backlog.vychozi') }}</td>
            <td class="mono">{{ a.model ?? t('backlog.vychozi') }}</td>
            <td>{{ a.thinking ?? t('backlog.vychozi') }}</td>
          </tr>
        </tbody>
      </table>
    </details>

    <p class="faint hint" data-test="run-continuation-hint">
      {{ t('backlog.automaticke_pokracovani_ridi_nastaveni_repozitare_na') }} <a :href="OVERVIEW_HREF">{{ t('backlog.prehledu') }}</a>.
    </p>

    <label class="note">
      <span>{{ t('backlog.poznamka_volitelna') }}</span>
      <textarea v-model="note" data-test="run-note" rows="3" :disabled="busy" />
    </label>

    <IssueList v-if="error" :code="error.code" :message="error.message" :issues="error.issues" />

    <p v-if="result" class="success" data-test="run-result">
      <template v-if="result.run">
        {{ t('backlog.runLabel') }} <span class="mono">{{ result.run.run_id }}</span> {{ t('backlog.spusten') }}
        <a :href="runHref(result.run.run_id)" class="button-link" data-test="run-open">{{ t('backlog.otevrit_beh') }}</a>
      </template>
      <template v-else>{{ t('backlog.beh_se_spousti') }}</template>
    </p>

    <div class="actions">
      <button
        type="button"
        class="primary"
        data-test="run-start"
        :disabled="blocked || blocking.length > 0"
        :aria-busy="action === 'start' || undefined"
        @click="start(false)"
      >
        <Spinner v-if="action === 'start'" />
        {{ t('backlog.spustit') }}
      </button>
      <button type="button" data-test="run-cancel" :disabled="busy" @click="cancel">
        {{ t('backlog.zavrit') }}
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
