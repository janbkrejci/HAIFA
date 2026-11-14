<script setup lang="ts">
import { t } from '@/lib/i18n'
import OverviewReadiness from '@/components/OverviewReadiness.vue'
const emit = defineEmits<{ changed: [] }>()
</script>

<template>
  <section data-test="system-problems">
    <h1>{{ t('dashboard.problemsTitle') }}</h1>
    <OverviewReadiness @changed="emit('changed')" />
  </section>
</template>
