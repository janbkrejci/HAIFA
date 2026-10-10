<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { Library, TriangleAlert } from 'lucide-vue-next'
import { fetchLibrarySummary } from '@/lib/library'

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
  <a v-if="exists" href="#/library" class="status-chip success" data-test="library-chip-ok"><Library :size="14" aria-hidden="true" /> Knihovna OK</a>
  <a v-else-if="exists === false" href="#/setup" class="status-chip warning" data-test="library-chip-missing"><TriangleAlert :size="14" aria-hidden="true" /> Založit knihovnu</a>
</template>

<style scoped>
.status-chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid currentColor; border-radius: 999px; padding: 5px 10px; font: inherit; font-size: 12px; white-space: nowrap; background: var(--panel-2); text-decoration: none; cursor: pointer; }
.status-chip:hover { background: var(--surface); }
.success { color: var(--green); }
.warning { color: var(--amber); }
</style>
