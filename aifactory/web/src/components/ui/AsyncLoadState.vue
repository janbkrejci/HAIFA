<script setup lang="ts">
import { t } from '@/lib/i18n'
defineProps<{ error?: Error }>()
function reload() { window.location.reload() }
</script>

<template>
  <div v-if="error" role="alert">
    <p>{{ t('common.screenError') }}</p>
    <button type="button" @click="reload">{{ t('common.reload') }}</button>
  </div>
  <p v-else role="status" aria-live="polite">{{ t('common.loading') }}</p>
</template>
