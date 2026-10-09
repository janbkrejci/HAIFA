<script setup lang="ts">
// #/r/<id>/factory: `factory check` of the repo (GET /api/repos/<id>/factory/check) with the
// manifest, the package version and the onboarding, and the findings in two groups: fix in the
// repo and commit, or fix on this machine. Writes use a reviewed and confirmed server plan.
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RefreshCw } from 'lucide-vue-next'
import { fetchFactoryCheck, type CheckFinding, type CheckSeverity, type FactoryCheck } from '@/lib/api'
import { errorText, fmtTime, shortSha } from '@/lib/format'
import { factoryStateText, onboardingText } from '@/lib/repos'
import OnboardingPanel from '@/components/factory/OnboardingPanel.vue'
import FactoryOperation from '@/components/factory/FactoryOperation.vue'
import FactoryFindingRepair from '@/components/factory/FactoryFindingRepair.vue'
import { lastFactoryResult } from '@/lib/factory'
import { NEW_CONTAINER, currentRepoId, repoHref, useRouteParams } from '@/lib/router'
import type { FactoryAction } from '@/lib/api'
import Spinner from '@/components/ui/Spinner.vue'
import FactoryItems from '@/components/factory/FactoryItems.vue'
import RosterEditor from '@/components/factory/RosterEditor.vue'

const SEVERITY_ORDER: Record<CheckSeverity, number> = { error: 0, warning: 1, info: 2 }
const SEVERITY_TEXT: Record<CheckSeverity, string> = { error: 'chyba', warning: 'varování', info: 'info' }

const completed = computed(() => lastFactoryResult.value?.repoId === repoId ? lastFactoryResult.value.result : null)
const operation = ref<FactoryAction | null>(null)
const repair = ref<CheckFinding[] | null>(null)
const operationSerial = ref(0)
/** Install just finished here: what to do next. */
const installed = computed(() => completed.value !== null && lastFactoryResult.value?.action === 'init')
const rosterBusy = ref(false)
const rosterSection = ref<HTMLElement | null>(null)
function showRoster() { rosterSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
function openOperation(action: FactoryAction) {
  if (operationBusy.value || itemsBusy.value || rosterBusy.value || repair.value) return
  operation.value = action
  ++operationSerial.value
}
function openConfig() { openOperation('config_commit') }
const operationBusy = ref(false)
const itemsBusy = ref(false)
const itemManager = ref<InstanceType<typeof FactoryItems> | null>(null)
const repoId = currentRepoId() ?? ''
const params = useRouteParams()
watch(params, value => { if(value[0] === 'config_commit') openConfig() }, { immediate: true })
const report = ref<FactoryCheck | null>(null)
const selected = ref<number[]>([])
function openRepair() {
  if (loading.value || error.value || operationBusy.value || itemsBusy.value || repair.value || !selected.value.length) return
  repair.value = selected.value.map(i => findings.value[i]).filter((f): f is CheckFinding => !!f)
  operation.value = null
}
const loading = ref(true) // the check starts on mount
const error = ref<string | null>(null)
let generation = 0

async function load(fresh = false): Promise<void> {
  const mine = ++generation
  loading.value = true
  error.value = null
  try {
    const data = await fetchFactoryCheck({ fresh })
    if (mine === generation) { report.value = data; selected.value = [] }
  } catch (err) {
    if (mine === generation) error.value = errorText(err)
  } finally {
    if (mine === generation) loading.value = false
  }
}

function sorted(findings: CheckFinding[]): CheckFinding[] {
  return [...findings].sort((a, b) => (SEVERITY_ORDER[a.severity] ?? 3) - (SEVERITY_ORDER[b.severity] ?? 3))
}

const findings = computed(() => report.value?.findings ?? [])
const groups = computed(() => [
  {
    id: 'repo',
    title: 'Repozitář: opravit a commitnout',
    items: sorted(findings.value.filter((f) => f.scope === 'repo')),
  },
  {
    id: 'local',
    title: 'Tento počítač: opravit lokálně',
    items: sorted(findings.value.filter((f) => f.scope !== 'repo')),
  },
])

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
    <section v-if="installed" class="next-steps" data-test="factory-next-steps">
      <h2>Co dál</h2>
      <ol>
        <li>Zkontroluj harnessy a modely agentů. <button type="button" class="btn" data-test="next-roster" @click="showRoster">Harnessy a modely</button></li>
        <li>Commitni konfiguraci, běhy čtou jen commitnutou base. <button type="button" class="btn" :disabled="operationBusy" data-test="next-commit" @click="openConfig">Commitnout konfiguraci</button></li>
        <li>Založ první projekt v backlogu. <a :href="repoHref(repoId, 'backlog', NEW_CONTAINER)" class="btn" data-test="next-project">Založit projekt</a></li>
      </ol>
    </section>
    <template v-if="report">
      <div class="actions" :inert="repair || itemsBusy || rosterBusy ? true : undefined">
        <button v-if="report.state === 'none'" type="button" class="btn" :disabled="operationBusy" data-test="factory-open-init" @click="openOperation('init')">Nainstalovat factory</button>
        <button v-if="report.state !== 'none'" type="button" class="btn" :disabled="operationBusy" data-test="factory-open-update" @click="openOperation('update')">Aktualizovat z knihovny</button>
        <button type="button" class="btn" :disabled="operationBusy" data-test="factory-open-config_commit" @click="openOperation('config_commit')">Commitnout konfiguraci</button>
        <button v-if="completed?.pr || (report.behind ?? 0) > 0 || report.findings.some(f => f.code === 'base_behind')" type="button" class="btn" :disabled="operationBusy" data-test="factory-open-pull" @click="openOperation('pull')">Stáhnout konfiguraci z base</button>
      </div>
      <div class="summary" data-test="factory-summary">
        <p class="verdict" :class="report.ok ? 'is-ok' : 'is-bad'" data-test="factory-verdict">
          <template v-if="report.ok">Factory je v pořádku</template>
          <template v-else>{{ report.counts.error }} chyb, {{ report.counts.warning }} varování</template>
        </p>
        <dl class="rows">
          <dt>Stav repa</dt>
          <dd data-test="factory-state">{{ factoryStateText(report.onboarding_state ?? report.state, report.onboarding_pr?.id) }}</dd>
          <dt>Manifest</dt>
          <dd data-test="factory-manifest">
            <template v-if="report.manifest">formát {{ report.manifest.format }}, zapsal {{ report.manifest.written_by }}</template>
            <template v-else>bez manifestu</template>
            <span v-if="report.manifest_error" class="error-inline" data-test="factory-manifest-error">
              ({{ report.manifest_error }})
            </span>
          </dd>
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
          <template v-if="report.onboarding">
            <dt>Onboarding</dt>
            <dd data-test="factory-onboarding">{{ onboardingText(report.onboarding) }} · knihovna {{ report.library?.name ?? '—' }}</dd>
          </template>
          <dt>Zkontrolováno</dt>
          <dd data-test="factory-checked">
            {{ fmtTime(report.checked_at) }}<template v-if="report.cached"> (z mezipaměti)</template>
          </dd>
        </dl>
        <p v-if="report.sssf_leftover" class="warn" data-test="factory-sssf-leftover">
          V repu zůstaly soubory instalace sssf.
        </p>
        <p v-if="report.alternate_rosters" class="warn" data-test="factory-alternate-rosters">
          V repu jsou další soupisky agentů vedle .factory/agents.yaml.
        </p>
      </div>

      <OnboardingPanel v-if="report.state === 'onboarded' || report.state === 'sssf' || report.state === 'pre_library'" :key="`${repoId}-${report.state}`" :disabled="!!operation || itemsBusy || !!repair" :repo-id="repoId" :action="report.state === 'onboarded' ? 'adopt' : 'onboard'" @busy="operationBusy = $event" @success="load(true)" />

      <div v-if="findings.length" class="repair-actions">
        <span data-test="factory-selected-count">Vybráno: {{ selected.length }}</span>
        <button type="button" class="btn" data-test="factory-repair-open"
          :disabled="!selected.length || loading || !!error || operationBusy || !!repair || itemsBusy" @click="openRepair">Vyřešit vybrané nálezy</button>
      </div>
      <section v-for="group in groups" :key="group.id" class="group" :data-test="`findings-${group.id}`">
        <h2>{{ group.title }}</h2>
        <p v-if="!group.items.length" class="none">Bez nálezů</p>
        <ul v-else class="findings">
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
            <span v-if="f.scope === 'library'" class="tag" data-test="finding-library">knihovna</span>
            <span class="code mono">{{ f.code }}</span>
            <span class="message">{{ f.message }}</span>
            <span v-if="f.fix" class="fix">Oprava: {{ f.fix }}</span>
          </li>
        </ul>
      </section>
    </template>
    <div v-if="report && report.state !== 'none'" ref="rosterSection">
      <RosterEditor readonly :repo-id="repoId" :disabled="operationBusy || itemsBusy || !!repair" />
    </div>
    <FactoryItems ref="itemManager" :repo-id="repoId" :disabled="operationBusy || rosterBusy || !!repair" @busy="itemsBusy = $event; if ($event) operation = null" @success="load(true)" />
    <FactoryFindingRepair v-if="repair" :findings="repair" @close="repair = null" />
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

h2 {
  margin: 0 0 8px;
  color: var(--dim);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
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

.tag {
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--purple);
  font-size: 12px;
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

.none,
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

.error-inline {
  color: var(--red);
}
</style>
