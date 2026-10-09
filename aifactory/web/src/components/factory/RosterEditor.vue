<script setup lang="ts">
// "Harnessy a modely" of the Factory tab: the harness, model and thinking of every agent in
// .factory/agents.yaml (GET /api/repos/<id>/factory/roster), a preset for all agents, and the
// read-only overrides on workflow steps. A change is previewed (dry_run) before it is saved to
// the working tree; runs read the committed base, so they use it after a config commit.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  fetchFactoryRoster, fetchMachineCheck, saveFactoryRoster,
  type FactoryRoster, type FactoryRosterAgent, type RosterBinding, type RosterChange, type RosterChangeResult,
} from '@/lib/api'
import { errorText } from '@/lib/format'
import { repoHref } from '@/lib/router'
import { PRESET_LABELS, detectedHarnesses, modelSuggestions, rosterChoices } from '@/lib/roster'
import DiffContent from '@/components/review/DiffContent.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ repoId: string; disabled?: boolean; readonly?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; saved: []; commit: [] }>()

interface Row { harness: string; model: string; thinking: string }

const roster = ref<FactoryRoster | null>(null)
const machineHarnesses = ref<string[]>([])
const loading = ref(false)
const error = ref('')
const rows = ref<Record<string, Row>>({})
/** The change under review: its request and the server's dry run. */
const pending = ref<{ change: Omit<RosterChange, 'dry_run'>; label: string; result: RosterChangeResult } | null>(null)
const working = ref(false)
const saved = ref(false)
let generation = 0

const choices = computed(() => rosterChoices(roster.value))
const agents = computed<FactoryRosterAgent[]>(() => roster.value?.agents ?? [])
const overrides = computed(() => roster.value?.workflow_overrides ?? [])
const models = computed(() => modelSuggestions(choices.value.presets, agents.value.map((a) => a.model)))
const harnessOptions = computed(() => {
  const names = [...new Set([...machineHarnesses.value, ...Object.values(choices.value.presets).map((p) => p.harness),
    ...agents.value.map(harnessOf).filter(Boolean)])]
  return [{ value: '', label: 'Podle výchozích' }, ...names.map((n) => ({ value: n, label: n }))]
})
const thinkingOptions = computed(() => [{ value: '', label: 'Podle výchozích' }, ...choices.value.thinking.map((t) => ({ value: t, label: t }))])
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

/** The fields of a row that differ from the roster; null when nothing changed. */
function rowChange(agent: FactoryRosterAgent): Omit<RosterChange, 'dry_run'> | null {
  const row = rows.value[agent.name]
  if (!row) return null
  const before = original(agent)
  const change: Omit<RosterChange, 'dry_run'> = { agent: agent.name }
  for (const key of ['harness', 'model', 'thinking'] as const) {
    if (row[key].trim() !== before[key]) change[key] = row[key].trim()
  }
  return Object.keys(change).length > 1 ? change : null
}

/** A changed field that is empty: the roster cannot drop a value, only set one. */
function rowBlank(agent: FactoryRosterAgent): boolean {
  const change = rowChange(agent)
  return !!change && (['harness', 'model', 'thinking'] as const).some((k) => k in change && !change[k])
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
    rows.value = Object.fromEntries(data.agents.map((a) => [a.name, original(a)]))
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

async function preview(change: Omit<RosterChange, 'dry_run'>, label: string): Promise<void> {
  if (locked.value) return
  working.value = true
  error.value = ''
  saved.value = false
  try {
    const result = await saveFactoryRoster({ ...change, dry_run: true }, props.repoId)
    pending.value = { change, label, result }
  } catch (err) {
    error.value = errorText(err)
  } finally {
    working.value = false
  }
}

function previewPreset(name: string): Promise<void> {
  return preview({ preset: name }, `Preset ${PRESET_LABELS[name] ?? name} pro všechny agenty`)
}

function previewAgent(agent: FactoryRosterAgent): Promise<void> {
  const change = rowChange(agent)
  return change ? preview(change, `Agent ${agent.name}`) : Promise.resolve()
}

function discard(): void {
  pending.value = null
  rows.value = Object.fromEntries(agents.value.map((a) => [a.name, original(a)]))
}

async function save(): Promise<void> {
  if (!pending.value || working.value) return
  working.value = true
  error.value = ''
  try {
    await saveFactoryRoster({ ...pending.value.change, dry_run: false }, props.repoId)
    pending.value = null
    saved.value = true
    emit('saved')
    await load()
  } catch (err) {
    error.value = errorText(err)
  } finally {
    working.value = false
  }
}

watch(() => working.value || !!pending.value, (value) => emit('busy', value))
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
    <h2>{{ readonly ? 'Definice agentů' : 'Harnessy a modely' }}</h2>
    <p v-if="readonly" class="hint">Výchozí harnessy a modely nastavíš tlačítkem s usage limity nahoře. Přepsat je může projekt a potom task.</p>
    <p v-else class="hint">Preset nastaví stejný harness, model a přemýšlení všem agentům. Úpravy se zapíšou do .factory/agents.yaml v pracovním stromu.</p>
    <p v-if="loading && !roster" class="loading"><Spinner /> Načítám agenty…</p>
    <p v-if="error" role="alert" class="error" data-test="roster-error">{{ error }}</p>

    <div v-if="!readonly" class="presets">
      <button
        v-for="(preset, name) in choices.presets"
        :key="name"
        type="button"
        class="btn"
        :disabled="locked"
        :data-test="`roster-preset-${name}`"
        @click="previewPreset(String(name))"
      >{{ PRESET_LABELS[name] ?? name }} <small>{{ preset.model }}</small></button>
    </div>

    <datalist :id="`roster-models-${repoId}`"><option v-for="m in models" :key="m" :value="m" /></datalist>
    <div v-if="agents.length" class="table">
      <table data-test="roster-agents">
        <thead><tr><th>Agent</th><th>Harness</th><th>Model</th><th>Přemýšlení</th><th /></tr></thead>
        <tbody>
          <tr v-for="agent in agents" :key="agent.name" :data-test="`roster-agent-${agent.name}`">
            <td>{{ agent.name }}<small v-if="agent.purpose" class="purpose">{{ agent.purpose }}</small></td>
            <template v-if="readonly"><td>{{ agent.harness ?? agent.coding_agent }}</td><td>{{ agent.model }}</td><td>{{ agent.thinking }}</td><td /></template>
            <template v-else-if="rows[agent.name]">
              <td><SelectMenu v-model="rows[agent.name]!.harness" :label="`Harness agenta ${agent.name}`" :options="harnessOptions" :disabled="locked" data-test="roster-harness" /></td>
              <td><input v-model="rows[agent.name]!.model" :list="`roster-models-${repoId}`" :aria-label="`Model agenta ${agent.name}`" placeholder="Podle výchozích" :disabled="locked" data-test="roster-model" /></td>
              <td><SelectMenu v-model="rows[agent.name]!.thinking" :label="`Přemýšlení agenta ${agent.name}`" :options="thinkingOptions" :disabled="locked" data-test="roster-thinking" /></td>
              <td>
                <button v-if="rowChange(agent)" type="button" class="btn" :disabled="locked || rowBlank(agent)" data-test="roster-preview" @click="previewAgent(agent)">Náhled změny</button>
                <small v-if="rowBlank(agent)" class="note">Hodnotu nejde smazat, jen změnit.</small>
              </td>
            </template>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else-if="roster" class="note">Roster nemá žádné agenty.</p>

    <section v-if="pending" class="pending" data-test="roster-pending">
      <h3>Náhled: {{ pending.label }}</h3>
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

    <p v-if="saved" class="ok" data-test="roster-saved">
      Uloženo. Běhy použijí změnu až po commitu konfigurace.
      <a :href="repoHref(repoId, 'factory', 'config_commit')" data-test="roster-commit" @click.prevent="emit('commit')">Commitnout konfiguraci</a>
    </p>

    <h3>Přepisy na krocích workflow</h3>
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
.roster { margin: 24px 0; padding: 16px 20px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); }
h2 { margin: 0 0 8px; color: var(--dim); font-size: 14px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
h3 { margin: 18px 0 8px; font-size: 15px; }
.hint, .note, .loading { color: var(--dim); font-size: 14px; }
.loading { display: flex; align-items: center; gap: 8px; }
.presets, .actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 10px 0; }
.table { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 6px 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }
th { color: var(--dim); font-weight: 600; }
.purpose { display: block; color: var(--faint); }
input { max-width: 200px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); color: var(--text); font: inherit; }
.btn { display: inline-flex; align-items: center; gap: 6px; padding: 5px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); font: inherit; font-size: 14px; cursor: pointer; }
.btn:disabled { cursor: default; opacity: 0.6; }
.btn.ok { border-color: rgba(74, 222, 128, 0.55); color: var(--green); font-weight: 700; }
.pending { margin-top: 12px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 10px; }
.ok { color: var(--green); }
.ok a { margin-left: 6px; color: var(--blue); }
.error { color: var(--red); }
</style>
