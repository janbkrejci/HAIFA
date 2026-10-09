<script setup lang="ts">
// #/setup "Tento počítač": the machine check in groups, the shared library (set up, pull, push),
// the dashboard's own settings and the first-visit guide.
import { computed, onMounted, ref } from 'vue'
import { fetchMachineCheck, type CheckSeverity, type MachineCheck } from '@/lib/api'
import { fetchLibrary, previewLibrary, applyLibrary, syncLibrary, FINDING_GROUPS, findingGroup, type LibraryStatus, type LibraryPlan, type LibraryRequest } from '@/lib/library'
import { errorText, fmtTime, plural } from '@/lib/format'
import { REPOS_ADD_HREF } from '@/lib/router'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import GettingStarted from '@/components/GettingStarted.vue'
import PlanView from '@/components/factory/PlanView.vue'
import DashboardSettings from '@/components/setup/DashboardSettings.vue'

const SEVERITY_TEXT: Record<CheckSeverity, string> = { error: 'chyba', warning: 'varování', info: 'info' }
const SYNC_TEXT = { pull: 'Stažení', push: 'Odeslání' } as const

const report = ref<MachineCheck | null>(null)
const library = ref<LibraryStatus | null>(null)
/** What the page waits for: reading the check, or writing the library. */
const busy = ref<'load' | 'write' | null>(null)
const error = ref('')
const copied = ref('')
const result = ref('')
const url = ref('')
const plan = ref<LibraryPlan | null>(null)
const request = ref<LibraryRequest | null>(null)
const groups = computed(() => FINDING_GROUPS.map(name => ({ name, findings: report.value?.findings.filter(f => findingGroup(f) === name) ?? [] })))

function harnessCount(name: string): string {
  const n = report.value?.harness_repos?.[name] ?? 0
  return `${name} · ${n === 0 ? 'nepoužívá žádné repo' : `${n} ${plural(n, 'repo', 'repa', 'rep')}`}`
}

async function load(fresh = false) {
  busy.value = 'load'
  error.value = ''
  const [check, lib] = await Promise.allSettled([fetchMachineCheck(fresh), fetchLibrary()])
  const errors: string[] = []
  if (check.status === 'fulfilled') report.value = check.value
  else errors.push(`Kontrola počítače selhala: ${errorText(check.reason)}`)
  if (lib.status === 'fulfilled') library.value = lib.value
  else errors.push(`Knihovnu se nepodařilo načíst: ${errorText(lib.reason)}`)
  error.value = errors.join(' · ')
  busy.value = null
}
async function copy(text: string, key: string) {
  try { await navigator.clipboard.writeText(text); copied.value = key }
  catch (e) { error.value = errorText(e) }
}
async function preview(action: 'init' | 'clone') {
  busy.value = 'write'; error.value = ''; result.value = ''
  const body: LibraryRequest = { action, options: action === 'clone' ? { url: url.value } : {} }
  try { plan.value = await previewLibrary(body); request.value = body }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = null }
}
async function apply() {
  if (busy.value || !plan.value || !request.value || plan.value.blockers.length) return
  busy.value = 'write'; error.value = ''
  let failed = ''
  try {
    const data = await applyLibrary(request.value, plan.value.digest)
    result.value = `Knihovna připravena${data.commit ? ' · commit ' + data.commit : ''}`
  } catch (e) { failed = errorText(e) }
  finally { plan.value = null; request.value = null; busy.value = null }
  await load(true)
  if (failed) error.value = failed
}
async function sync(action: 'pull' | 'push') {
  if (busy.value) return
  busy.value = 'write'; error.value = ''; result.value = ''
  let failed = ''
  try { await syncLibrary(action); result.value = `${SYNC_TEXT[action]} dokončeno` }
  catch (e) { failed = errorText(e) }
  finally { busy.value = null }
  await load(true)
  if (failed) error.value = failed
}
onMounted(() => { void load() })
</script>
<template>
  <section class="global-page" data-test="setup">
    <header><h1>Tento počítač</h1><button :disabled="!!busy" data-test="machine-refresh" @click="load(true)">Znovu zkontrolovat</button></header>
    <GettingStarted :check="report" :library="library" />
    <p v-if="error" role="alert" data-test="setup-error">{{ error }}</p>
    <p v-if="result" role="status">{{ result }}</p>
    <p v-if="busy" data-test="setup-busy">{{ busy === 'write' ? 'Ukládám…' : 'Načítám…' }}</p>
    <p v-if="report">Kontrola: {{ fmtTime(report.checked_at) }}{{ report.cached ? ' · z mezipaměti' : '' }}</p>
    <section v-for="group in groups" :key="group.name" :data-group="group.name">
      <h2>{{ group.name }}</h2>
      <p v-if="report && !group.findings.length">Bez nálezů</p>
      <p v-if="group.name === 'HAIFA'">HAIFA je spuštěná na tomto počítači.</p>
      <ul v-if="group.name === 'Harnessy'" data-test="harness-counts"><li v-for="name in Object.keys(report?.harness_repos ?? { claude: 0, codex: 0, pi: 0 })" :key="name">{{ harnessCount(name) }}</li></ul>
      <article v-for="(f, index) in group.findings" :key="f.code + index" :class="f.severity" data-test="machine-finding">
        <strong>{{ SEVERITY_TEXT[f.severity] ?? f.severity }} · {{ f.code }}</strong><p>{{ f.message }}</p>
        <template v-if="f.fix">
          <p>{{ f.fix }}</p>
          <button data-test="copy-fix" @click="copy(f.fix, f.code + index)">{{ copied === f.code + index ? 'Zkopírováno' : 'Kopírovat' }}</button>
        </template>
        <p v-else>Zkontroluj nastavení prostředí podle nálezu.</p>
      </article>
      <template v-if="group.name === 'Knihovna' && library">
        <template v-if="library.exists">
          <p data-test="library-path">{{ library.library }}</p>
          <p>Remote: {{ library.remote ?? 'Bez remote · lokální knihovna' }}</p>
          <p>Napřed: {{ library.ahead ?? '—' }} · Pozadu: {{ library.behind ?? '—' }}</p>
          <button :disabled="!!busy || !library.remote" data-test="library-pull" @click="sync('pull')">Stáhnout</button>
          <button :disabled="!!busy || !library.remote" data-test="library-push" @click="sync('push')">Odeslat</button>
          <a href="#/library">Otevřít knihovnu</a>
        </template>
        <template v-else>
          <label>URL týmové knihovny <input v-model="url" data-test="library-url" placeholder="https://…/library.git" :disabled="!!busy" /></label>
          <button :disabled="!!busy || !url.trim()" data-test="library-clone" @click="preview('clone')">Naklonovat týmovou knihovnu…</button>
          <button :disabled="!!busy" data-test="library-init" @click="preview('init')">Založit ze semínka</button>
        </template>
      </template>
    </section>
    <DashboardSettings />
    <p class="next"><a :href="REPOS_ADD_HREF" class="next-step" data-test="add-repo-link">Další krok: Přidat repozitář</a> · <a href="#/overview">Přehled</a></p>
    <ConfirmDialog :open="!!plan" :title="request?.action === 'clone' ? 'Naklonovat týmovou knihovnu' : 'Založit knihovnu ze semínka'" confirm-label="Potvrdit plán" :confirm-disabled="!!busy || !!plan?.blockers.length" @confirm="apply" @cancel="!busy && (plan = null)">
      <PlanView v-if="plan" :plan="plan" collapsed data-test="library-plan">
        <p v-if="plan.library">{{ typeof plan.library === 'string' ? plan.library : plan.library.name }}</p>
      </PlanView>
    </ConfirmDialog>
  </section>
</template>
<style src="./library.css" />
<style scoped>
.next-step { font-weight: 700; }
</style>
