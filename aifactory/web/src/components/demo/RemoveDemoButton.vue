<script setup lang="ts">
import { t } from '@/lib/i18n'
import { deferredError } from '@/lib/dashboardMessages'
import { feedbackText } from '@/components/overview/feedback'
// "Odebrat ukázku": after a confirmation, the sample leaves the dashboard and its folder is
// deleted (DELETE /api/demo); then the overview opens.
import { ref } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import { useConfirm } from '@/lib/confirm'
import { lastStart, removeDemo, useDemoRepo } from '@/lib/demo'
import { OVERVIEW_HREF } from '@/lib/router'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ path?: string | null }>()
// without a path of its own, the folder of the open sample
const demoPath = useDemoRepo()
const { dialog, ask, confirm, cancel } = useConfirm()
const removalPath = ref('')
const busy = ref(false)
const error = ref<string | (() => string) | null>(null)

async function remove() {
  error.value = null
  const path = props.path || demoPath.value
  removalPath.value = path ? ` ${path}` : ''
  const ok = await ask({
    title: t('dashboard.removeDemoTitle'),
    message: t('dashboard.removeDemoBody', { path: path ? ` ${path}` : '' }),
    confirmLabel: t('dashboard.removeDemo'),
    cancelLabel: t('common.cancel'),
    tone: 'danger',
  })
  if (!ok) return
  busy.value = true
  try {
    await removeDemo()
    lastStart.value = null
    window.location.hash = OVERVIEW_HREF
    window.dispatchEvent(new Event('factory-applied'))
  } catch (err) {
    error.value = deferredError(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="remove-demo">
    <button type="button" class="remove-button" :disabled="busy" :aria-busy="busy || undefined" data-test="remove-demo" @click="remove">
      <Spinner v-if="busy" /><Trash2 v-else :size="14" aria-hidden="true" /> {{ t('dashboard.removeDemo') }}
    </button>
    <span v-if="error" class="remove-error" role="alert" data-test="remove-demo-error">{{ t('dashboard.removeDemoFailed') }} {{ feedbackText(error) }}</span>
  </span>
  <ConfirmDialog v-bind="dialog" :title="t('dashboard.removeDemoTitle')"
      :message="t('dashboard.removeDemoBody', { path: removalPath })"
      :confirm-label="t('dashboard.removeDemo')" :cancel-label="t('common.cancel')" @confirm="confirm" @cancel="cancel" />
</template>

<style scoped>
.remove-demo { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.remove-button { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); font: inherit; cursor: pointer; }
.remove-button:disabled { cursor: default; opacity: 0.7; }
.remove-error { color: var(--red); }
</style>
