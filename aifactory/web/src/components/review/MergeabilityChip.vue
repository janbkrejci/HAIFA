<script setup lang="ts">
import { t } from '@/lib/i18n'
import { computed } from 'vue'
import type { Mergeability } from '@/lib/review'

const props = defineProps<{ value: Mergeability | string | null }>()

const LABELS = computed<Record<string, string>>(() => ({
  mergeable: t('review.mergeable'),
  conflict: t('review.conflict'),
  unknown: t('review.unknown'),
}))

const cls = computed(() => (props.value && props.value in LABELS.value ? props.value : 'unknown'))
const label = computed(() => LABELS.value[cls.value])
</script>

<template>
  <span class="mchip" :class="cls" data-test="mergeability" :data-value="cls">{{ label }}</span>
</template>

<style scoped>
.mchip {
  display: inline-flex;
  padding: 2px 11px;
  border-radius: 999px;
  border: 1px solid var(--border);
  font-size: 15px;
  color: var(--dim);
  white-space: nowrap;
}

.mchip.mergeable {
  color: var(--green);
  border-color: rgba(74, 222, 128, 0.45);
  background: rgba(74, 222, 128, 0.09);
}

.mchip.conflict {
  color: var(--red);
  border-color: rgba(255, 111, 103, 0.45);
  background: rgba(255, 111, 103, 0.09);
}

.mchip.unknown {
  border-style: dashed;
}
</style>
