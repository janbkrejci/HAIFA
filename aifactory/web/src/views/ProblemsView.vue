<script setup lang="ts">
import OverviewReadiness from '@/components/OverviewReadiness.vue'
const emit = defineEmits<{ changed: [] }>()
</script>

<template>
  <section data-test="system-problems">
    <h1>Problémy a řešení</h1>
    <OverviewReadiness @changed="emit('changed')" />
  </section>
</template>
