<script setup lang="ts">
// #/setup "Knihovna" (opened from the library chip of the topbar): the library in $HAIFA_HOME
// first (#/setup/library scrolls to it), then the check of this computer (only findings that need
// an action, in groups) and the dashboard's own settings. Library findings show in the library section.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fetchMachineCheck, type MachineCheck } from '@/lib/api'
import { MACHINE_GROUPS, findingGroup } from '@/lib/library'
import { errorText, fmtTime } from '@/lib/format'
import { CHECK_DEADLINE_MS, PROGRESS_SHOWN_AFTER, beforeDeadline, followProgress, lastKnown, serverStep } from '@/lib/machineProgress'
import { useRouteParams } from '@/lib/router'
import DashboardSettings from '@/components/setup/DashboardSettings.vue'
import LibrarySection from '@/components/setup/LibrarySection.vue'
import MachineFinding from '@/components/setup/MachineFinding.vue'

const report = ref<MachineCheck | null>(null)
const loading = ref(false)
const error = ref('')
const findings = computed(() => report.value?.findings ?? [])
const libraryFindings = computed(() => findings.value.filter(f => f.scope === 'library'))
const groups = computed(() => MACHINE_GROUPS
  .map(name => ({ name, findings: findings.value.filter(f => f.scope !== 'library' && findingGroup(f) === name) }))
  .filter(group => group.findings.length > 0))
const counts = computed(() => ({
  error: findings.value.filter(f => f.severity === 'error').length,
  warning: findings.value.filter(f => f.severity === 'warning').length,
}))

/** The server's step and the elapsed seconds of the running check, once it takes a while. */
const step = ref<string | null>(null)
const elapsed = ref(0)
const progress = computed(() => elapsed.value >= PROGRESS_SHOWN_AFTER ? `${step.value ?? 'kontrola počítače'} · ${elapsed.value} s` : '')
/** The shown result is the last known one of a check that did not finish. */
const timeout = computed(() => {
  const r = report.value
  if (!r?.timed_out) return ''
  const unfinished = serverStep(r.progress) ?? 'kontrola počítače'
  const known = lastKnown(r.checked_at)
  return `Kontrola nedoběhla do ${r.progress?.budget ?? Math.round(CHECK_DEADLINE_MS / 1000)} s. Nedokončený krok: ${unfinished}. `
    + (known ? `Zobrazen poslední známý výsledek ${known}.` : 'Dřívější výsledek není k dispozici.')
})
let generation = 0
let stopProgress: (() => void) | undefined

async function load(fresh = false) {
  const current = ++generation
  loading.value = true
  error.value = ''
  stopProgress?.()
  step.value = null
  elapsed.value = 0
  stopProgress = followProgress((seconds, server) => { elapsed.value = seconds; step.value = server }, () => true)
  const seconds = Math.round(CHECK_DEADLINE_MS / 1000)
  try {
    const result = await beforeDeadline(fetchMachineCheck(fresh), Date.now() + CHECK_DEADLINE_MS, () => step.value ?? 'kontrola počítače', seconds)
    // A later answer of an older check never replaces a newer result.
    if (current === generation) report.value = result
  } catch (e) {
    if (current === generation) error.value = `Kontrola počítače selhala: ${errorText(e)}`
  } finally {
    if (current === generation) {
      loading.value = false
      stopProgress?.()
      stopProgress = undefined
    }
  }
}
onBeforeUnmount(() => stopProgress?.())

/** After a library write: read the updated library rules and let the topbar chips follow. */
async function onLibraryChanged() {
  await load()
  window.dispatchEvent(new Event('factory-applied'))
}

const params = useRouteParams()
async function showLibrary() {
  await nextTick()
  document.getElementById('library')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
watch(params, value => { if (value[0] === 'library') void showLibrary() }, { immediate: true })

onMounted(() => { void load() })
</script>
<template>
  <section class="global-page" data-test="setup">
    <header><h1>Knihovna</h1></header>
    <LibrarySection :findings="libraryFindings" @changed="onLibraryChanged" />
    <section data-test="machine-check">
      <header><h2>Kontrola počítače</h2><button :disabled="loading" data-test="machine-refresh" @click="load(true)">Znovu zkontrolovat</button></header>
      <p v-if="error" role="alert" data-test="setup-error">{{ error }}</p>
      <p v-if="loading" data-test="setup-busy">{{ progress ? `Probíhá kontrola – čeká na: ${progress}` : 'Načítám…' }}</p>
      <p v-if="!loading && timeout" role="alert" data-test="machine-timeout">{{ timeout }}</p>
      <p v-if="!loading && report && !timeout && (report.checked === false || report.stale)" role="alert" data-test="machine-status">{{ report.checked === false ? 'Počítač zatím nebyl zkontrolován.' : 'Zastaralý výsledek kontroly počítače.' }} Pro aktuální stav spusť ruční kontrolu tlačítkem Znovu zkontrolovat.</p>
      <div v-if="report && report.checked_at" class="summary" data-test="machine-summary">
        <p class="verdict" :class="counts.error || report.timed_out || report.stale ? 'is-bad' : 'is-ok'" data-test="machine-verdict">
          <template v-if="report.timed_out || report.stale">Poslední známý stav: </template>
          <template v-if="!counts.error && !counts.warning">Počítač je v pořádku</template>
          <template v-else>{{ counts.error }} chyb, {{ counts.warning }} varování</template>
        </p>
        <p class="hint">Zkontrolováno: {{ fmtTime(report.checked_at) }}{{ report.cached ? ' (z mezipaměti)' : '' }}<template v-if="report.stale"> – {{ lastKnown(report.checked_at) }}, neaktuální</template><template v-if="report.library_stale"> – stav knihovny se nepodařilo načíst znovu</template></p>
      </div>
      <section v-for="group in groups" :key="group.name" :data-group="group.name">
        <h3>{{ group.name }}</h3>
        <MachineFinding v-for="(f, index) in group.findings" :key="f.code + index" :finding="f" />
      </section>
    </section>
    <DashboardSettings />
  </section>
</template>
<style src="./library.css" />
<style scoped>
.summary { margin: 16px 0; }
[data-test=machine-check] h2 { margin: 0; }
.verdict { margin: 0 0 4px; font-size: 17px; font-weight: 700; }
.is-ok { color: var(--green); }
.is-bad { color: var(--red); }
</style>
