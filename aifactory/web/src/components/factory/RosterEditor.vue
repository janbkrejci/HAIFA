<script setup lang="ts">
// The agents of "Vybavení továrny" on the Factory tab (GET /api/repos/<id>/factory/roster): every
// agent once, with its harness, model and thinking and whether each value is inherited (library
// and roster defaults) or overridden in .factory/agents.yaml. "Upravit" sets an override, "Vrátit
// na zděděné" removes it (`reset`); each change is previewed (dry_run) under its agent before it
// is saved to the working tree. Runs read the committed base, so they use it after a config
// commit (the red config chip in the topbar). Below: the read-only overrides on workflow steps.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchFactoryRoster, fetchMachineCheck, saveFactoryRoster,
  type FactoryRoster, type FactoryRosterAgent, type RosterBinding, type RosterChange, type RosterChangeResult,
  type RosterField,
} from '@/lib/api'
import { useConfigStatus } from '@/lib/configStatus'
import { errorText } from '@/lib/format'
import { detectedHarnesses, modelSuggestions, rosterChoices } from '@/lib/roster'
import DiffContent from '@/components/review/DiffContent.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ repoId: string; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; saved: []; move: [name: string] }>()

interface Row { harness: string; model: string; thinking: string }
const FIELDS: readonly RosterField[] = ['harness', 'model', 'thinking']

const roster = ref<FactoryRoster | null>(null)
const machineHarnesses = ref<string[]>([])
const loading = ref(false)
const error = ref('')
/** The agent whose row is being edited. */
const editing = ref<string | null>(null)
const row = ref<Row>({ harness: '', model: '', thinking: '' })
/** The change under review: its request and the server's dry run. */
const pending = ref<{ agent: string; change: Omit<RosterChange, 'dry_run'>; label: string; result: RosterChangeResult } | null>(null)
const working = ref(false)
const saved = ref(false)
const configStatus = useConfigStatus()
let generation = 0

const choices = computed(() => rosterChoices(roster.value))
const agents = computed<FactoryRosterAgent[]>(() => roster.value?.agents ?? [])
const overrides = computed(() => roster.value?.workflow_overrides ?? [])
const models = computed(() => modelSuggestions(choices.value.presets, agents.value.map((a) => a.model)))
const harnessOptions = computed(() => {
  const names = [...new Set([...machineHarnesses.value, ...Object.values(choices.value.presets).map((p) => p.harness),
    ...agents.value.map(harnessOf).filter(Boolean)])]
  return names.map((n) => ({ value: n, label: n }))
})
const thinkingOptions = computed(() => choices.value.thinking.map((t) => ({ value: t, label: t })))
const locked = computed(() => !!props.disabled || working.value || loading.value || !!pending.value)
const changedBindings = computed(() => {
  if (!pending.value) return []
  const before = new Map(pending.value.result.before.map((a) => [a.name, a]))
  return pending.value.result.agents.filter((a) => {
    const b = before.get(a.name)
    return !b || b.harness !== a.harness || b.model !== a.model || b.thinking !== a.thinking
  }).map((a) => ({ after: a, before: before.get(a.name) ?? null }))
})

function harnessOf(agent: FactoryRosterAgent): string {
  return agent.harness ?? agent.coding_agent ?? ''
}

function original(agent: FactoryRosterAgent): Row {
  return { harness: harnessOf(agent), model: agent.model ?? '', thinking: agent.thinking ?? '' }
}

function value(agent: FactoryRosterAgent, field: RosterField): string {
  return original(agent)[field]
}

function isOverridden(agent: FactoryRosterAgent, field: RosterField): boolean {
  return (agent.overridden ?? []).includes(field)
}

/** The overrides "Vrátit na zděděné" removes: only a library agent has inherited values. */
function resettable(agent: FactoryRosterAgent): RosterField[] {
  return agent.inherited ? FIELDS.filter((f) => isOverridden(agent, f)) : []
}

/** The fields of the edited row that differ from the roster; null when nothing changed. */
function rowChange(agent: FactoryRosterAgent): Omit<RosterChange, 'dry_run'> | null {
  if (editing.value !== agent.name) return null
  const before = original(agent)
  const change: Omit<RosterChange, 'dry_run'> = { agent: agent.name }
  for (const key of FIELDS) {
    if (row.value[key].trim() !== before[key]) change[key] = row.value[key].trim()
  }
  return Object.keys(change).length > 1 ? change : null
}

/** A changed field that is empty: an override cannot be blank; "Vrátit na zděděné" removes it. */
function rowBlank(agent: FactoryRosterAgent): boolean {
  const change = rowChange(agent)
  return !!change && FIELDS.some((k) => k in change && !change[k])
}

function binding(b: RosterBinding | null): string {
  return b ? `${b.harness} · ${b.model} · ${b.thinking}` : '—'
}

async function load(): Promise<void> {
  const mine = ++generation
  loading.value = true
  error.value = ''
  try {
    const data = await fetchFactoryRoster(props.repoId)
    if (mine !== generation) return
    roster.value = data
  } catch (err) {
    if (mine === generation) error.value = errorText(err)
  } finally {
    if (mine === generation) loading.value = false
  }
}

async function loadHarnesses(): Promise<void> {
  try {
    const check = await fetchMachineCheck()
    machineHarnesses.value = detectedHarnesses(check)
  } catch {
    // the harnesses of the presets and the roster are still offered
  }
}

function edit(agent: FactoryRosterAgent): void {
  if (locked.value) return
  saved.value = false
  editing.value = agent.name
  row.value = original(agent)
}

function cancel(): void {
  editing.value = null
}

async function preview(agent: string, change: Omit<RosterChange, 'dry_run'>, label: string): Promise<void> {
  if (locked.value) return
  working.value = true
  error.value = ''
  saved.value = false
  try {
    const result = await saveFactoryRoster({ ...change, dry_run: true }, props.repoId)
    pending.value = { agent, change, label, result }
  } catch (err) {
    error.value = errorText(err)
  } finally {
    working.value = false
  }
}

function previewAgent(agent: FactoryRosterAgent): Promise<void> {
  const change = rowChange(agent)
  return change ? preview(agent.name, change, `Agent ${agent.name}`) : Promise.resolve()
}

function previewReset(agent: FactoryRosterAgent): Promise<void> {
  const reset = resettable(agent)
  if (!reset.length) return Promise.resolve()
  editing.value = null
  return preview(agent.name, { agent: agent.name, reset }, `Agent ${agent.name}: návrat na zděděné hodnoty`)
}

function discard(): void {
  pending.value = null
}

async function save(): Promise<void> {
  if (!pending.value || working.value) return
  working.value = true
  error.value = ''
  try {
    await saveFactoryRoster({ ...pending.value.change, dry_run: false }, props.repoId)
    pending.value = null
    editing.value = null
    saved.value = true
    emit('saved')
    void configStatus.refresh()
    await load()
  } catch (err) {
    error.value = errorText(err)
  } finally {
    working.value = false
  }
}

watch(() => working.value || !!pending.value, (busy) => emit('busy', busy))
onMounted(() => {
  void load()
  void loadHarnesses()
})
onBeforeUnmount(() => {
  ++generation
  emit('busy', false)
})
defineExpose({ reload: load })
</script>

<template>
  <section class="roster" data-test="roster-editor">
    <p class="hint">Harness, model a přemýšlení se dědí z knihovny a výchozích hodnot projektu. Přepis se zapíše do .factory/agents.yaml v pracovním stromu a jde vrátit na zděděnou hodnotu.</p>
    <p v-if="loading && !roster" class="loading"><Spinner /> Načítám agenty…</p>
    <p v-if="error" role="alert" class="error" data-test="roster-error">{{ error }}</p>

    <datalist :id="`roster-models-${repoId}`"><option v-for="m in models" :key="m" :value="m" /></datalist>
    <div v-if="agents.length" class="table">
      <table data-test="roster-agents">
        <thead><tr><th>Agent</th><th>Harness</th><th>Model</th><th>Přemýšlení</th><th /></tr></thead>
        <tbody>
          <template v-for="agent in agents" :key="agent.name">
            <tr :data-test="`roster-agent-${agent.name}`" :class="{ editing: editing === agent.name }">
              <td>
                <span class="mono">{{ agent.name }}</span>
                <span v-if="agent.origin === 'repo'" class="origin own" data-test="roster-own">vlastní kopie</span>
                <span v-else class="origin" data-test="roster-origin">z knihovny</span>
                <small v-if="agent.purpose" class="purpose">{{ agent.purpose }}</small>
              </td>
              <template v-if="editing === agent.name">
                <td><SelectMenu v-model="row.harness" :label="`Harness agenta ${agent.name}`" :options="harnessOptions" :disabled="locked" data-test="roster-harness" /></td>
                <td><input v-model="row.model" :list="`roster-models-${repoId}`" :aria-label="`Model agenta ${agent.name}`" :disabled="locked" data-test="roster-model" /></td>
                <td><SelectMenu v-model="row.thinking" :label="`Přemýšlení agenta ${agent.name}`" :options="thinkingOptions" :disabled="locked" data-test="roster-thinking" /></td>
                <td class="row-actions">
                  <button type="button" class="btn" :disabled="locked || !rowChange(agent) || rowBlank(agent)" data-test="roster-preview" @click="previewAgent(agent)">Náhled změny</button>
                  <button type="button" class="btn" :disabled="working || !!pending" data-test="roster-cancel" @click="cancel">Zrušit</button>
                  <small v-if="rowBlank(agent)" class="note">Hodnotu nejde smazat, jen změnit. K zděděné hodnotě vede Vrátit na zděděné.</small>
                </td>
              </template>
              <template v-else>
                <td v-for="field in FIELDS" :key="field" :data-test="`roster-${field}-value`">
                  <span class="mono">{{ value(agent, field) || '—' }}</span>
                  <template v-if="agent.inherited">
                    <Tooltip v-if="isOverridden(agent, field)" :text="`Zděděno: ${agent.inherited[field]}`">
                      <span class="state overridden" tabindex="0" :data-test="`roster-overridden-${field}`">přepsáno</span>
                    </Tooltip>
                    <span v-else class="state" :data-test="`roster-inherited-${field}`">zděděno</span>
                  </template>
                </td>
                <td class="row-actions">
                  <button type="button" class="btn" :disabled="locked || editing !== null" data-test="roster-edit" @click="edit(agent)">Upravit</button>
                  <button v-if="resettable(agent).length" type="button" class="btn" :disabled="locked || editing !== null"
                    data-test="roster-reset" @click="previewReset(agent)">Vrátit na zděděné</button>
                  <button v-if="agent.origin === 'repo'" type="button" class="btn" :disabled="locked || editing !== null"
                    :data-test="`item-move-agent-${agent.name}`" @click="emit('move', agent.name)">Přesunout do knihovny</button>
                </td>
              </template>
            </tr>
            <tr v-if="pending?.agent === agent.name" class="pending-row">
              <td colspan="5">
                <section class="pending" data-test="roster-pending">
                  <h4>Náhled: {{ pending.label }}</h4>
                  <p v-if="!pending.result.changed" data-test="roster-unchanged">Roster už takhle nastavený je, není co uložit.</p>
                  <ul v-if="changedBindings.length" data-test="roster-changes">
                    <li v-for="c in changedBindings" :key="c.after.name">{{ c.after.name }}: {{ binding(c.before) }} → {{ binding(c.after) }}</li>
                  </ul>
                  <DiffContent v-if="pending.result.diff" :patch="pending.result.diff" />
                  <div class="actions">
                    <button type="button" class="btn ok" :disabled="working || !pending.result.changed" data-test="roster-save" @click="save">
                      <Spinner v-if="working" /> Uložit
                    </button>
                    <button type="button" class="btn" :disabled="working" data-test="roster-discard" @click="discard">Zrušit</button>
                  </div>
                </section>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
    <p v-else-if="roster" class="note">Roster nemá žádné agenty.</p>

    <p v-if="saved" class="ok" data-test="roster-saved">
      Uloženo. Běhy použijí změnu až po commitu konfigurace (červený čip v horní liště).
    </p>

    <h4>Přepisy na krocích workflow</h4>
    <p class="hint">Krok workflow může mít vlastní harness nebo model. Ten má přednost před rosterem i před volbou pro jeden běh.</p>
    <table v-if="overrides.length" data-test="roster-overrides">
      <thead><tr><th>Workflow</th><th>Krok</th><th>Agent</th><th>Harness</th><th>Model</th><th>Přemýšlení</th></tr></thead>
      <tbody>
        <tr v-for="o in overrides" :key="`${o.workflow}/${o.step}`">
          <td>{{ o.workflow }}</td><td>{{ o.step }}</td><td>{{ o.agent ?? '—' }}</td><td>{{ o.harness ?? '—' }}</td><td>{{ o.model ?? '—' }}</td><td>{{ o.thinking ?? '—' }}</td>
        </tr>
      </tbody>
    </table>
    <p v-else class="note" data-test="roster-no-overrides">Žádný krok workflow nemá vlastní harness ani model.</p>
  </section>
</template>

<style scoped>
.roster { margin: 0; }
h4 { margin: 18px 0 8px; font-size: 14px; }
.hint, .note, .loading { color: var(--dim); font-size: 14px; }
.loading { display: flex; align-items: center; gap: 8px; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0 0; }
.table { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
th { color: var(--dim); font-weight: 600; }
tr.editing td { background: var(--panel-2); }
.pending-row td { padding: 0 8px 10px; }
.purpose { display: block; color: var(--faint); }
.origin { margin-left: 6px; padding: 0 6px; border: 1px solid var(--border); border-radius: 6px; color: var(--dim); font-size: 12px; }
.origin.own { color: var(--purple); }
.state { margin-left: 6px; color: var(--faint); font-size: 12px; }
.state.overridden { padding: 0 6px; border: 1px solid var(--amber); border-radius: 6px; color: var(--amber); font-weight: 600; }
.row-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
input { max-width: 200px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); color: var(--text); font: inherit; }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); color: var(--text); font: inherit; font-size: 13px; cursor: pointer; }
.btn:disabled { cursor: default; opacity: 0.6; }
.btn.ok { border-color: rgba(74, 222, 128, 0.55); color: var(--green); font-weight: 700; }
.pending { padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; }
.pending h4 { margin-top: 0; }
.ok { color: var(--green); }
.error { color: var(--red); }
</style>
