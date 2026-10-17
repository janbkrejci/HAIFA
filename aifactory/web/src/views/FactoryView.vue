<script setup lang="ts">
// #/r/<id>/factory: everything about the factory of one repo. `factory check` of the repo
// (GET /api/repos/<id>/factory/check) with the package version, and the findings in two
// groups: fix in the repo and commit, or fix on this machine for this repo. Machine findings
// the machine check (#/setup) shows too and the library findings live only there; one line
// links to them; "Vyřešit vybrané nálezy" opens its panel right under that button, next to the
// findings. Below: the repo settings (#/r/<id>/factory/settings) and "Nastavení agentů" (the
// repo-level harness, model and thinking of each agent) and "Lekce" (the lessons of `factory
// learn`, LessonsSection). Every section collapses by its heading;
// a jump to a section (Co dál, #/r/<id>/factory/settings) opens it first. The config commit (#/r/<id>/factory/config_commit) is opened by the red config chip in the topbar.
// Writes use a reviewed and confirmed server plan.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { fetchFactoryCheck, fetchMachineCheck, type CheckFinding, type CheckSeverity, type FactoryCheck } from '@/lib/api'
import { errorText, fmtTime, shortSha } from '@/lib/format'
import { factoryStateText } from '@/lib/repos'
import FactoryOperation from '@/components/factory/FactoryOperation.vue'
import FactoryFindingRepair from '@/components/factory/FactoryFindingRepair.vue'
import { lastFactoryResult } from '@/lib/factory'
import { NEW_CONTAINER, SETUP_HREF, currentRepoId, repoHref, useRouteParams } from '@/lib/router'
import type { FactoryAction } from '@/lib/api'
import Spinner from '@/components/ui/Spinner.vue'
import RepoItems from '@/components/factory/RepoItems.vue'
import RepoSettings from '@/components/factory/RepoSettings.vue'
import LessonsSection from '@/components/factory/LessonsSection.vue'
import CollapsibleSection from '@/components/ui/CollapsibleSection.vue'

const SEVERITY_ORDER: Record<CheckSeverity, number> = { error: 0, warning: 1, info: 2 }
const SEVERITY_TEXT: Record<CheckSeverity, string> = { error: 'chyba', warning: 'varování', info: 'info' }

const completed = computed(() => lastFactoryResult.value?.repoId === repoId ? lastFactoryResult.value.result : null)
const operation = ref<FactoryAction | null>(null)
const repair = ref<CheckFinding[] | null>(null)
const operationSerial = ref(0)
/** Install just finished here: what to do next. */
const installed = computed(() => completed.value !== null && lastFactoryResult.value?.action === 'init')
const rosterSection = ref<HTMLElement | null>(null)
const repairSection = ref<HTMLElement | null>(null)
/** Which sections are expanded; a finding group by its id. */
const nextOpen = ref(true)
const summaryOpen = ref(true)
const settingsOpen = ref(true)
const agentsOpen = ref(true)
const lessonsOpen = ref(true)
const groupOpen = ref<Record<string, boolean>>({})
async function showRoster() {
  agentsOpen.value = true
  await nextTick()
  rosterSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function openOperation(action: FactoryAction) {
  if (operationBusy.value || itemsBusy.value || repair.value) return
  operation.value = action
  ++operationSerial.value
}
function openConfig() { openOperation('config_commit') }
const operationBusy = ref(false)
const itemsBusy = ref(false)
const itemManager = ref<InstanceType<typeof RepoItems> | null>(null)
const repoId = currentRepoId() ?? ''
const params = useRouteParams()
const settingsSection = ref<HTMLElement | null>(null)
/** `#/r/<id>/factory/settings` scrolls to the repo settings once they are shown. */
let scrollToSettings = false
async function showSettings() {
  settingsOpen.value = true
  await nextTick()
  if (!settingsSection.value) return
  scrollToSettings = false
  settingsSection.value.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
watch(params, value => {
  if (value[0] === 'config_commit') openConfig()
  if (value[0] === 'settings') { scrollToSettings = true; void showSettings() }
}, { immediate: true })
const report = ref<FactoryCheck | null>(null)
const selected = ref<number[]>([])
async function openRepair() {
  if (loading.value || error.value || operationBusy.value || itemsBusy.value || repair.value || !selected.value.length) return
  repair.value = selected.value.map(i => findings.value[i]).filter((f): f is CheckFinding => !!f)
  operation.value = null
  await nextTick()
  repairSection.value?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' })
}
const loading = ref(true) // the check starts on mount
const error = ref<string | null>(null)
let generation = 0

async function load(fresh = false): Promise<void> {
  const mine = ++generation
  loading.value = true
  error.value = null
  try {
    // The machine check only hides what #/setup shows; without it nothing is hidden.
    const [data, machine] = await Promise.all([
      fetchFactoryCheck({ fresh }),
      fetchMachineCheck().catch(() => null),
    ])
    if (mine === generation) {
      report.value = data
      machineFindings.value = machine?.findings ?? null
      selected.value = []
      if (scrollToSettings) void showSettings()
    }
  } catch (err) {
    if (mine === generation) error.value = errorText(err)
  } finally {
    if (mine === generation) loading.value = false
  }
}

function sorted(findings: CheckFinding[]): CheckFinding[] {
  return [...findings].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3))
}

const machineFindings = ref<CheckFinding[] | null>(null)
/** A finding #/setup shows: any library finding, a machine finding the machine check has too. */
function elsewhere(f: CheckFinding): boolean {
  if (f.scope === 'library') return true
  if (f.scope !== 'machine' || machineFindings.value === null) return false
  return machineFindings.value.some((m) => m.code === f.code && m.message === f.message)
}
/** The findings shown here; their indices are what the checkboxes select. */
const findings = computed(() => (report.value?.findings ?? []).filter((f) => !elsewhere(f)))
const hidden = computed(() => (report.value?.findings ?? []).filter(elsewhere))
const counts = computed(() => {
  const result: Record<CheckSeverity, number> = { error: 0, warning: 0, info: 0 }
  for (const f of findings.value) result[f.severity] = (result[f.severity] ?? 0) + 1
  return result
})
const verdictOk = computed(() => counts.value.error === 0)
const groups = computed(() => [
  {
    id: 'repo',
    title: 'Repozitář: opravit a commitnout',
    items: sorted(findings.value.filter((f) => f.scope === 'repo')),
  },
  {
    id: 'local',
    title: 'Počítač: potřebné pro toto repo',
    items: sorted(findings.value.filter((f) => f.scope !== 'repo')),
  },
].filter((group) => group.items.length > 0))

function short(sha: string | null): string {
  return shortSha(sha, 8) || '—'
}

onMounted(() => { void load(); window.addEventListener('factory-commit-preview', openConfig) })
onBeforeUnmount(() => { ++generation; window.removeEventListener('factory-commit-preview', openConfig) })
</script>

<template>
  <section class="factory-view">
    <div class="head">
      <h1>Factory</h1>
      <button type="button" class="btn" :disabled="loading || !!repair" data-test="factory-recheck" @click="load(true); itemManager?.reload()">
        <RefreshCw :size="14" aria-hidden="true" :class="{ spin: loading }" /> Znovu zkontrolovat
      </button>
    </div>

    <FactoryOperation v-if="operation" :key="operationSerial" :action="operation" :repo-id="repoId" :remote="report?.remote" @busy="operationBusy = $event" @success="load(true); itemManager?.reload()" />

    <p v-if="loading && !report" class="loading" data-test="factory-loading"><Spinner /> Kontroluji factory…</p>
    <p v-if="error" class="error" data-test="factory-error">Kontrola factory selhala: {{ error }}</p>

    <div v-if="completed" data-test="factory-completed">
      <p v-if="completed.library_commit">Commit knihovny: {{ completed.library_commit }}</p>
      <p>Hotovo: {{ completed.commit ?? completed.after }}</p>
      <template v-if="completed.pr"><a :href="completed.pr.url" target="_blank" rel="noopener">Otevřít PR</a><p>Běhy počkají na merge. Po merge použij Stáhnout konfiguraci z base.</p></template>
      <a :href="repoHref(repoId,'backlog')">Otevřít backlog</a>
    </div>
    <CollapsibleSection v-if="installed" v-model:open="nextOpen" heading="Co dál" class="next-steps" data-test="factory-next-steps">
      <ol>
        <li>Zkontroluj harnessy a modely agentů. <button type="button" class="btn" data-test="next-roster" @click="showRoster">Nastavení agentů</button></li>
        <li data-test="next-commit-hint">Commitni konfiguraci červeným čipem „Necommitnutá konfigurace“ v horní liště, běhy čtou jen commitnutou base.</li>
        <li>Založ první projekt v backlogu. <a :href="repoHref(repoId, 'backlog', NEW_CONTAINER)" class="btn" data-test="next-project">Založit projekt</a></li>
      </ol>
    </CollapsibleSection>
    <template v-if="report">
      <div class="actions" :inert="repair || itemsBusy ? true : undefined">
        <button v-if="report.state === 'none'" type="button" class="btn" :disabled="operationBusy" data-test="factory-open-init" @click="openOperation('init')">Nainstalovat factory</button>
        <button v-if="completed?.pr || (report.behind ?? 0) > 0 || report.findings.some(f => f.code === 'base_behind')" type="button" class="btn" :disabled="operationBusy" data-test="factory-open-pull" @click="openOperation('pull')">Stáhnout konfiguraci z base</button>
      </div>
      <CollapsibleSection v-model:open="summaryOpen" heading="Souhrn kontroly" data-test="factory-summary">
        <div class="summary">
        <p class="verdict" :class="verdictOk ? 'is-ok' : 'is-bad'" data-test="factory-verdict">
          <template v-if="verdictOk">Factory je v pořádku</template>
          <template v-else>{{ counts.error }} chyb, {{ counts.warning }} varování</template>
        </p>
        <dl class="rows">
          <dt>Stav repa</dt>
          <dd data-test="factory-state">{{ factoryStateText(report.state) }}</dd>
          <dt>Verze balíčku</dt>
          <dd class="mono" data-test="factory-version">{{ report.version }}</dd>
          <template v-if="report.base">
            <dt>Base</dt>
            <dd class="mono" data-test="factory-base">
              {{ report.base }}@{{ short(report.commit) }}
              <template v-if="report.ahead !== null && report.behind !== null">
                · napřed {{ report.ahead }}, pozadu {{ report.behind }}
              </template>
            </dd>
          </template>
          <dt>Zkontrolováno</dt>
          <dd data-test="factory-checked">
            {{ fmtTime(report.checked_at) }}<template v-if="report.cached"> (z mezipaměti)</template>
          </dd>
        </dl>
        </div>
      </CollapsibleSection>

      <div v-if="findings.length" class="repair-actions">
        <span data-test="factory-selected-count">Vybráno: {{ selected.length }}</span>
        <button type="button" class="btn" data-test="factory-repair-open"
          :disabled="!selected.length || loading || !!error || operationBusy || !!repair || itemsBusy" @click="openRepair">Vyřešit vybrané nálezy</button>
      </div>
      <div v-if="repair" ref="repairSection" class="repair-section">
        <FactoryFindingRepair :findings="repair" @close="repair = null" />
      </div>
      <CollapsibleSection v-for="group in groups" :key="group.id" :open="groupOpen[group.id] ?? true" :heading="group.title"
        class="group" :data-test="`findings-${group.id}`" @update:open="groupOpen[group.id] = $event">
        <ul class="findings">
          <li
            v-for="(f, i) in group.items"
            :key="`${f.code}-${i}`"
            class="finding"
            data-test="finding"
            :data-severity="f.severity"
          >
            <input v-model="selected" type="checkbox" :value="findings.indexOf(f)"
              :aria-label="`Vybrat nález ${f.code}: ${f.message}`" data-test="finding-select"
              :disabled="loading || !!error || operationBusy || !!repair || itemsBusy" />
            <span class="severity" :class="`sev-${f.severity}`">{{ SEVERITY_TEXT[f.severity] ?? f.severity }}</span>
            <span class="code mono">{{ f.code }}</span>
            <span class="message">{{ f.message }}</span>
            <span v-if="f.fix" class="fix">Oprava: {{ f.fix }}</span>
          </li>
        </ul>
      </CollapsibleSection>
      <p v-if="hidden.length" class="elsewhere" data-test="factory-machine-link">
        Další nálezy tohoto počítače a knihovny: {{ hidden.length }}<template v-if="hidden.some(f => f.severity === 'error')"> (s chybami)</template>
        · <a :href="SETUP_HREF">Otevřít stránku Knihovna</a>
      </p>
    </template>
    <section v-if="report && report.state !== 'none'" ref="settingsSection" data-test="factory-settings">
      <RepoSettings v-model:open="settingsOpen" @saved="load(true)" />
    </section>
    <div v-if="report && report.state !== 'none'" ref="rosterSection">
      <RepoItems ref="itemManager" v-model:open="agentsOpen" :repo-id="repoId" :disabled="operationBusy || !!repair" @busy="itemsBusy = $event; if ($event) operation = null" @success="load(true)" />
    </div>
    <LessonsSection v-if="report && report.state !== 'none'" v-model:open="lessonsOpen" :disabled="operationBusy || !!repair || itemsBusy" />
  </section>
</template>

<style scoped>
.factory-view {
  padding: 28px;
  max-width: 1200px;
  margin: 0 auto;
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0 0 18px;
}

h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.btn:disabled {
  cursor: default;
  opacity: 0.7;
}

.next-steps {
  margin: 0 0 18px;
  padding: 14px 20px;
  border: 1px solid rgba(74, 222, 128, 0.45);
  border-radius: 12px;
  background: var(--surface);
}

.next-steps ol {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding-left: 20px;
}

.next-steps .btn {
  margin-left: 8px;
  text-decoration: none;
}

.summary {
  padding: 16px 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.repair-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-top: 22px; }

.verdict {
  margin: 0 0 12px;
  font-size: 17px;
  font-weight: 700;
}

.is-ok {
  color: var(--green);
}

.is-bad {
  color: var(--red);
}

.rows {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 18px;
  margin: 0;
}

dt {
  color: var(--dim);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.group {
  margin-top: 22px;
}

.findings {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.finding {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 12px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.severity {
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
}

.sev-error {
  color: var(--red);
}

.sev-warning {
  color: var(--amber);
}

.sev-info {
  color: var(--blue);
}

.elsewhere {
  margin: 14px 0 0;
  color: var(--dim);
}

.code {
  color: var(--dim);
  font-size: 13px;
}

.message {
  flex: 1 1 320px;
}

.fix {
  flex-basis: 100%;
  color: var(--dim);
  font-size: 14px;
}

.loading {
  margin: 0;
  color: var(--dim);
}

.loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.warn {
  margin: 10px 0 0;
  color: var(--amber);
}

.error {
  color: var(--red);
}
</style>
