<script setup lang="ts">
// "Odebrat ukázku": after a confirmation, the sample leaves the dashboard and its folder is
// deleted (DELETE /api/demo); then the overview opens.
import { ref } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import { useConfirm } from '@/lib/confirm'
import { lastStart, removeDemo, useDemoRepo } from '@/lib/demo'
import { errorText } from '@/lib/format'
import { OVERVIEW_HREF } from '@/lib/router'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ path?: string | null }>()
// without a path of its own, the folder of the open sample
const demoPath = useDemoRepo()
const { dialog, ask, confirm, cancel } = useConfirm()
const busy = ref(false)
const error = ref<string | null>(null)

async function remove() {
  error.value = null
  const path = props.path || demoPath.value
  const ok = await ask({
    title: 'Odebrat ukázku?',
    message: `Ukázka zmizí z dashboardu a smaže se celá její složka${path ? ` ${path}` : ''} i s běhy a větvemi. Kdykoli ji můžeš vytvořit znovu.`,
    confirmLabel: 'Odebrat ukázku',
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
    error.value = errorText(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <span class="remove-demo">
    <button type="button" class="remove-button" :disabled="busy" :aria-busy="busy || undefined" data-test="remove-demo" @click="remove">
      <Spinner v-if="busy" /><Trash2 v-else :size="14" aria-hidden="true" /> Odebrat ukázku
    </button>
    <span v-if="error" class="remove-error" role="alert" data-test="remove-demo-error">Ukázku se nepodařilo odebrat: {{ error }}</span>
  </span>
  <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
</template>

<style scoped>
.remove-demo { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.remove-button { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); font: inherit; cursor: pointer; }
.remove-button:disabled { cursor: default; opacity: 0.7; }
.remove-error { color: var(--red); }
</style>
