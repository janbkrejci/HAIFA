<script setup lang="ts">
// The aifactory code on disk changed since the dashboard started (lib/code.ts): writes are off
// until the server restarts.
import Spinner from '@/components/ui/Spinner.vue'

defineProps<{ stale: boolean; restarting: boolean; error: string | null }>()
const emit = defineEmits<{ restart: [] }>()
</script>

<template>
  <div v-if="stale || error" class="code-banner" role="alert" data-test="code-banner">
    <p v-if="stale">
      Kód HAIFA se od spuštění dashboardu změnil. Zápisy jsou vypnuté, dokud dashboard
      nerestartuješ.
    </p>
    <p v-if="error" class="code-error" data-test="code-error">{{ error }}</p>
    <button
      v-if="stale"
      type="button"
      data-test="code-restart"
      :disabled="restarting"
      :aria-busy="restarting || undefined"
      @click="emit('restart')"
    >
      <Spinner v-if="restarting" />
      {{ restarting ? 'Restartuji…' : 'Restartovat dashboard' }}
    </button>
  </div>
</template>

<style scoped>
.code-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin: 12px 28px 0;
  padding: 8px 14px;
  border: 1px solid rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  background: rgba(232, 182, 74, 0.08);
  color: var(--amber);
}

.code-banner p {
  margin: 0;
}

.code-error {
  color: var(--text);
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface, transparent);
  color: var(--text);
  cursor: pointer;
}

button:disabled {
  cursor: default;
  opacity: 0.7;
}
</style>
