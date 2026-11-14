<script setup lang="ts">
defineProps<{ error?: Error }>()
function reload() { window.location.reload() }
</script>

<template>
  <div v-if="error" role="alert">
    <p>Obrazovku se nepodařilo načíst.</p>
    <button type="button" @click="reload">Načíst znovu</button>
  </div>
  <p v-else role="status" aria-live="polite">Načítám…</p>
</template>
