<script setup lang="ts">
import { intlLocale, t } from '@/lib/i18n'
import './ui/statusIconChip.css'
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
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
const errorMessage = shallowRef<() => string>(() => '')
const resultMessage = shallowRef<() => string>(() => '')
const error = computed(() => errorMessage.value())
const result = computed(() => resultMessage.value())
const { dialog, ask, confirm, cancel } = useConfirm()
let timer: ReturnType<typeof setInterval> | undefined
let disposed = false
const busy = computed(() => loading.value || cleaning.value)
const gb = (bytes: number | null) => bytes === null ? t('common.unavailable') : `${(bytes / 1024 ** 3).toLocaleString(intlLocale.value, { maximumFractionDigits: 2 })} GB`
const tooltip = computed(() => [
  t('system.title'),
  cleaning.value ? t('system.cleaning') : loading.value ? t('common.loading') : '',
  info.value ? t('system.disk', { free: gb(info.value.disk.free), total: gb(info.value.disk.total) }) : '',
  info.value ? t('system.memory', { free: gb(info.value.memory.free), total: gb(info.value.memory.total) }) : '',
  error.value,
  result.value,
  t('system.hint'),
].filter(Boolean).join('\n'))

async function load() {
  if (disposed || loading.value) return
  loading.value = true
  try {
    const data = await fetchSystemInfo()
    if (!data.disk || !data.memory) throw new Error('invalid_system_response')
    if (!disposed) { info.value = data; errorMessage.value = () => '' }
  } catch (err) {
    if (!disposed) errorMessage.value = () => t('system.loadError', { error: err instanceof Error && err.message === 'invalid_system_response' ? t('system.invalid') : errorText(err) })
  } finally {
    loading.value = false
  }
}

async function cleanup() {
  if (busy.value || dialog.open) return
  const accepted = await ask(() => ({
    title: t('system.confirm'),
    message: t('system.message'),
    confirmLabel: t('system.clean'),
    tone: 'danger',
  }))
  if (!accepted || disposed) return
  cleaning.value = true
  resultMessage.value = () => ''
  try {
    const data = await runCleanup()
    if (disposed) return
    const count = data.advice_directories.length + data.repos.reduce((sum, repo) => sum + repo.removed.length + repo.deleted_branches.length, 0)
    resultMessage.value = () => [t('system.result', { count, space: gb(data.freed_bytes) }, count), ...data.warnings].join('\n')
  } catch (err) {
    if (!disposed) resultMessage.value = () => t('system.failed', { error: errorText(err) })
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
