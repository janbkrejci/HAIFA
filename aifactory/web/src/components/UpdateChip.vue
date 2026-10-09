<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpCircle, Check, TriangleAlert } from 'lucide-vue-next'
import { useUpdates } from '@/lib/updates'
import Spinner from './ui/Spinner.vue'
import Tooltip from './ui/Tooltip.vue'

const updates = useUpdates()
const state = updates.state
const label = computed(() => ({
  checking: 'Kontrola aktualizací',
  current: 'Systém je aktuální',
  available: 'Je k dispozici aktualizace',
  error: 'Nepodařilo se zkontrolovat aktualizace',
  installing: 'Instaluji aktualizaci…',
})[state.value.status])
const hint = computed(() => state.value.error || (state.value.status === 'available'
  ? `Verze ${state.value.target_version}: kliknutím stáhneš a nainstaluješ aktualizaci, restartuješ dashboard a spustíš kontrolu systému.`
  : `${label.value}. Kliknutím zopakuješ kontrolu.`))
</script>

<template>
  <Tooltip :text="hint">
    <button type="button" class="update-chip" :class="state.status" :aria-label="label" :disabled="state.status === 'checking' || state.status === 'installing'" data-test="update-chip" @click="updates.activate">
      <Spinner v-if="state.status === 'checking' || state.status === 'installing'" />
      <Check v-else-if="state.status === 'current'" :size="14" aria-hidden="true" />
      <ArrowUpCircle v-else-if="state.status === 'available'" :size="14" aria-hidden="true" />
      <TriangleAlert v-else :size="14" aria-hidden="true" />
      <span>{{ label }}</span>
    </button>
  </Tooltip>
</template>

<style scoped>
.update-chip { display: inline-flex; align-items: center; gap: 6px; max-width: 195px; border: 1px solid currentColor; border-radius: 999px; padding: 5px 10px; font: inherit; font-size: 12px; background: var(--panel-2); white-space: nowrap; }
.update-chip span { overflow: hidden; text-overflow: ellipsis; }
.update-chip :deep(svg) { flex: none; }
.update-chip:disabled { opacity: 1; cursor: progress; }
.checking, .installing { color: var(--blue); }
.current { color: var(--green); }
.available, .error { color: var(--amber); }
@media (max-width: 1000px) { .update-chip { max-width: 145px; } }
</style>
