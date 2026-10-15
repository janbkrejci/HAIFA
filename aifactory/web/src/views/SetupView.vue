<script setup lang="ts">
// #/setup "Tento počítač": everything about this computer. The machine check (only findings
// that need an action, in groups), the library in $HAIFA_HOME (#/setup/library scrolls to it)
// and the dashboard's own settings. Library findings show in the library section.
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { fetchMachineCheck, type MachineCheck } from '@/lib/api'
import { MACHINE_GROUPS, findingGroup } from '@/lib/library'
import { errorText, fmtTime } from '@/lib/format'
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

async function load(fresh = false) {
  loading.value = true
  error.value = ''
  try { report.value = await fetchMachineCheck(fresh) }
  catch (e) { error.value = `Kontrola počítače selhala: ${errorText(e)}` }
  finally { loading.value = false }
}

/** After a write to the library: check again, and let the topbar chips follow. */
async function onLibraryChanged() {
  await load(true)
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
    <header><h1>Tento počítač</h1><button :disabled="loading" data-test="machine-refresh" @click="load(true)">Znovu zkontrolovat</button></header>
    <p v-if="error" role="alert" data-test="setup-error">{{ error }}</p>
    <p v-if="loading" data-test="setup-busy">Načítám…</p>
    <div v-if="report" class="summary" data-test="machine-summary">
      <p class="verdict" :class="counts.error ? 'is-bad' : 'is-ok'" data-test="machine-verdict">
        <template v-if="!counts.error && !counts.warning">Počítač je v pořádku</template>
        <template v-else>{{ counts.error }} chyb, {{ counts.warning }} varování</template>
      </p>
      <p class="hint">Zkontrolováno: {{ fmtTime(report.checked_at) }}{{ report.cached ? ' (z mezipaměti)' : '' }}</p>
    </div>
    <section v-for="group in groups" :key="group.name" :data-group="group.name">
      <h2>{{ group.name }}</h2>
      <MachineFinding v-for="(f, index) in group.findings" :key="f.code + index" :finding="f" />
    </section>
    <LibrarySection :findings="libraryFindings" @changed="onLibraryChanged" />
    <DashboardSettings />
  </section>
</template>
<style src="./library.css" />
<style scoped>
.summary { margin: 16px 0; }
.verdict { margin: 0 0 4px; font-size: 17px; font-weight: 700; }
.is-ok { color: var(--green); }
.is-bad { color: var(--red); }
</style>
