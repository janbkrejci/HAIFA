<script setup lang="ts">
import './ui/statusIconChip.css'
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
  waiting: 'Aktualizace čeká na tasky',
  error: 'Nepodařilo se zkontrolovat aktualizace',
  installing: 'Instaluji aktualizaci…',
})[state.value.status])
const hint = computed(() => state.value.error || (state.value.status === 'available'
  ? `Verze ${state.value.target_version}: kliknutím stáhneš a nainstaluješ aktualizaci, restartuješ dashboard a spustíš kontrolu systému.`
  : 'Kliknutím zopakuješ kontrolu.'))
const description = computed(() => `${label.value} – ${hint.value}`)
</script>

<template>
  <Tooltip :text="description">
    <button type="button" class="status-icon-chip update-chip" :class="state.status" :aria-label="description" :disabled="state.status === 'checking' || state.status === 'installing'" data-test="update-chip" @click="updates.activate">
      <Spinner v-if="state.status === 'checking' || state.status === 'installing'" />
      <Check v-else-if="state.status === 'current'" :size="14" aria-hidden="true" />
      <ArrowUpCircle v-else-if="state.status === 'available'" :size="14" aria-hidden="true" />
      <TriangleAlert v-else :size="14" aria-hidden="true" />
    </button>
  </Tooltip>
</template>

<style scoped>
.update-chip:disabled { opacity: 1; cursor: progress; }
.checking, .installing { color: var(--blue); }
.current { color: var(--green); }
.available, .waiting, .error { color: var(--amber); }
</style>
