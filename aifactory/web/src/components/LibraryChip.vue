<script setup lang="ts">
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
  <Tooltip v-if="exists" text="Knihovna OK – kliknutím otevřeš knihovnu"><a :href="LIBRARY_HREF" class="status-icon-chip success" aria-label="Knihovna OK – kliknutím otevřeš knihovnu" data-test="library-chip-ok"><Library :size="14" aria-hidden="true" /></a></Tooltip>
  <Tooltip v-else-if="exists === false" text="Založit knihovnu – kliknutím otevřeš knihovnu"><a :href="LIBRARY_HREF" class="status-icon-chip warning" aria-label="Založit knihovnu – kliknutím otevřeš knihovnu" data-test="library-chip-missing"><TriangleAlert :size="14" aria-hidden="true" /></a></Tooltip>
</template>

<style scoped>
.success { color: var(--green); }
.warning { color: var(--amber); }
</style>
