<script setup lang="ts">
import './ui/statusIconChip.css'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { HardDrive } from 'lucide-vue-next'
import { fetchSystemInfo, runCleanup, type SystemInfo } from '@/lib/system'
import { useConfirm } from '@/lib/confirm'
import { errorText } from '@/lib/format'
import ConfirmDialog from './ui/ConfirmDialog.vue'
import Spinner from './ui/Spinner.vue'
import Tooltip from './ui/Tooltip.vue'

const info = ref<SystemInfo | null>(null)
const loading = ref(false)
const cleaning = ref(false)
const error = ref('')
const result = ref('')
const { dialog, ask, confirm, cancel } = useConfirm()
let timer: ReturnType<typeof setInterval> | undefined
let disposed = false
const busy = computed(() => loading.value || cleaning.value)
const gb = (bytes: number | null) => bytes === null ? 'nedostupné' : `${(bytes / 1024 ** 3).toLocaleString('cs-CZ', { maximumFractionDigits: 2 })} GB`
const tooltip = computed(() => [
  'System info',
  cleaning.value ? 'Uklízím disk…' : loading.value ? 'Načítám…' : '',
  info.value ? `Disk: volné ${gb(info.value.disk.free)} / celkem ${gb(info.value.disk.total)}` : '',
  info.value ? `Paměť: volná ${gb(info.value.memory.free)} / celkem ${gb(info.value.memory.total)}` : '',
  error.value,
  result.value,
  'Kliknutím uklidíš disk',
].filter(Boolean).join('\n'))

async function load() {
  if (disposed || loading.value) return
  loading.value = true
  try {
    const data = await fetchSystemInfo()
    if (!data.disk || !data.memory) throw new Error('Neplatná odpověď systému')
    if (!disposed) { info.value = data; error.value = '' }
  } catch (err) {
    if (!disposed) error.value = `System info se nepodařilo načíst: ${errorText(err)}`
  } finally {
    loading.value = false
  }
}

async function cleanup() {
  if (busy.value || dialog.open) return
  const accepted = await ask({
    title: 'Uklidit disk?',
    message: 'Smažou se osiřelé dočasné adresáře návrhů a hotové worktrees a větve sloučených PR ve všech repech.',
    confirmLabel: 'Uklidit disk',
    tone: 'danger',
  })
  if (!accepted || disposed) return
  cleaning.value = true
  result.value = ''
  try {
    const data = await runCleanup()
    if (disposed) return
    const count = data.advice_directories.length + data.repos.reduce((sum, repo) => sum + repo.removed.length + repo.deleted_branches.length, 0)
    result.value = [`Úklid: odstraněno ${count} položek, uvolněné místo: ${gb(data.freed_bytes)}.`, ...data.warnings].join('\n')
  } catch (err) {
    if (!disposed) result.value = `Úklid se nepodařil: ${errorText(err)}`
  } finally {
    await load()
    cleaning.value = false
  }
}

onMounted(() => {
  void load()
  timer = setInterval(() => { if (!busy.value && !dialog.open) void load() }, 60_000)
})
onBeforeUnmount(() => { disposed = true; clearInterval(timer); cancel() })
</script>

<template>
  <Tooltip :text="tooltip">
    <button class="status-icon-chip info" type="button" :disabled="busy" :aria-label="tooltip" :aria-busy="busy" data-test="system-info-chip" @click="cleanup">
      <Spinner v-if="busy" />
      <HardDrive v-else :size="14" aria-hidden="true" />
    </button>
  </Tooltip>
  <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
</template>

<style scoped>
.info { color: var(--blue); }
</style>
