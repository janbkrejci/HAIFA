<script setup lang="ts">
// A project, step or task code with its title and level in the shared tooltip.
// The name comes from the shared map (lib/names.ts), so a rename shows up live.
import { computed } from 'vue'
import { nameTip } from '@/lib/names'
import Tooltip from './Tooltip.vue'

const props = defineProps<{ code: string | null | undefined }>()

const text = computed(() => nameTip(props.code))
</script>

<template>
  <Tooltip :text="text">
    <slot>{{ code }}</slot>
  </Tooltip>
</template>
