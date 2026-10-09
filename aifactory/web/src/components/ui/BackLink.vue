<script setup lang="ts">
// Shared "back to the list" link of the detail screens: arrow icon and text,
// both vertically centred on the neighbouring heading.
import { ArrowLeft } from 'lucide-vue-next'

defineProps<{ href: string; label: string }>()
</script>

<template>
  <a :href="href" class="back" data-test="back">
    <ArrowLeft :size="16" aria-hidden="true" data-test="back-icon" />
    <span>{{ label }}</span>
  </a>
</template>

<style scoped>
.back {
  display: inline-flex;
  align-items: center;
  align-self: center;
  gap: 6px;
  line-height: 1;
  color: var(--dim);
}

.back svg {
  flex: none;
}
</style>
