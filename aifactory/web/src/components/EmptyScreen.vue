<script setup lang="ts">
// A screen with nothing to show: title, hint and an optional link (slot).
defineProps<{ heading: string; hint: string }>()
</script>

<template>
  <section class="empty-screen">
    <h1>{{ heading }}</h1>
    <div class="panel">
      <p>{{ hint }}</p>
      <div v-if="$slots.default" class="actions">
        <slot />
      </div>
    </div>
  </section>
</template>

<style scoped>
.empty-screen {
  padding: 28px;
  max-width: 1200px;
  margin: 0 auto;
}

h1 {
  margin: 0 0 18px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.panel {
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
  color: var(--dim);
}

p {
  margin: 0;
}

.actions {
  margin-top: 14px;
}
</style>
