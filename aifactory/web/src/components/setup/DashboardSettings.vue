<script setup lang="ts">
import { errorText } from '../../lib/format'
// The dashboard section of #/setup (Tento počítač): its port (GET/POST /api/dashboard/settings, applies after
// a restart), the registry file and the home folder.
import { computed, onMounted, ref } from 'vue'
import { ApiError, fetchDashboardSettings, saveDashboardSettings, type DashboardSettings } from '@/lib/api'
import Spinner from '@/components/ui/Spinner.vue'

const settings = ref<DashboardSettings | null>(null)
const loadError = ref<string | null>(null)
const port = ref<number | string>('')
const saving = ref(false)
const saveError = ref<string | null>(null)
const restartNote = ref<string | null>(null)

const portNumber = computed(() => Number(port.value))
const valid = computed(
  () => port.value !== '' && Number.isInteger(portNumber.value) && portNumber.value >= 1 && portNumber.value <= 65535,
)
const changed = computed(() => settings.value !== null && portNumber.value !== settings.value.port)

onMounted(async () => {
  try {
    settings.value = await fetchDashboardSettings()
    port.value = settings.value.port
  } catch (err) {
    loadError.value = errorText(err)
  }
})

async function save() {
  if (!valid.value || !changed.value) return
  saving.value = true
  saveError.value = null
  restartNote.value = null
  try {
    const data = await saveDashboardSettings(portNumber.value)
    settings.value = data
    port.value = data.port
    if (data.restart_required) {
      restartNote.value = `Uloženo. Dashboard teď běží na jiném portu, nový port ${data.port} platí po restartu.`
    }
  } catch (err) {
    if (err instanceof ApiError) saveError.value = err.issues[0]?.message || err.message
    else saveError.value = errorText(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="dashboard-settings" data-test="dashboard-settings">
    <h2>Dashboard</h2>
    <p v-if="loadError" class="error" data-test="dash-error">Nastavení dashboardu se nepodařilo načíst: {{ loadError }}</p>
    <p v-else-if="!settings" class="loading"><Spinner /> Načítám nastavení…</p>
    <template v-else>
      <form class="port-row" @submit.prevent="save">
        <label for="dash-port">Port</label>
        <input
          id="dash-port"
          v-model="port"
          type="number"
          min="1"
          max="65535"
          class="port mono"
          data-test="dash-port"
        />
        <button type="submit" class="btn" :disabled="!valid || !changed || saving" data-test="dash-port-save">
          <Spinner v-if="saving" /> Uložit
        </button>
      </form>
      <p class="note">Port platí po restartu dashboardu.</p>
      <p v-if="restartNote" class="ok" data-test="dash-restart-note">{{ restartNote }}</p>
      <p v-if="saveError" class="error" data-test="dash-port-error">{{ saveError }}</p>
      <dl class="paths">
        <dt>Registr</dt>
        <dd class="mono" data-test="dash-registry">{{ settings.registry }}</dd>
        <dt>Domov</dt>
        <dd class="mono" data-test="dash-home">{{ settings.home }}</dd>
      </dl>
    </template>
  </section>
</template>

<style scoped>
.dashboard-settings {
  margin-top: 28px;
  padding: 18px 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

h2 {
  margin: 0 0 12px;
  font-size: 18px;
  font-weight: 700;
}

.port-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.port {
  width: 110px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-size: 15px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.note,
.loading {
  margin: 8px 0 0;
  color: var(--dim);
  font-size: 14px;
}

.loading {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ok {
  margin: 8px 0 0;
  color: var(--green);
}

.error {
  margin: 8px 0 0;
  color: var(--red);
}

.paths {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 18px;
  margin: 14px 0 0;
}

dt {
  color: var(--dim);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>
