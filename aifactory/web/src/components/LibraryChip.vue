<script setup lang="ts">
import { t } from '@/lib/i18n'
import './ui/statusIconChip.css'
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Library, TriangleAlert } from 'lucide-vue-next'
import { fetchLibrarySummary } from '@/lib/library'
import Tooltip from './ui/Tooltip.vue'
import { LIBRARY_HREF } from '@/lib/router'

/** Whether this computer has a library: null while unknown (or unreadable). */
const exists = ref<boolean | null>(null)

async function load() {
  try {
    exists.value = (await fetchLibrarySummary()).exists
  } catch {
    exists.value = null
  }
}

onMounted(() => {
  void load()
  window.addEventListener('factory-applied', load)
})
onBeforeUnmount(() => window.removeEventListener('factory-applied', load))
defineExpose({ load })
</script>

<template>
  <Tooltip v-if="exists" :text="t('library.ok')"><a :href="LIBRARY_HREF" class="status-icon-chip success" :aria-label="t('library.ok')" data-test="library-chip-ok"><Library :size="14" aria-hidden="true" /></a></Tooltip>
  <Tooltip v-else-if="exists === false" :text="t('library.missing')"><a :href="LIBRARY_HREF" class="status-icon-chip warning" :aria-label="t('library.missing')" data-test="library-chip-missing"><TriangleAlert :size="14" aria-hidden="true" /></a></Tooltip>
</template>

<style scoped>
.success { color: var(--green); }
.warning { color: var(--amber); }
</style>
