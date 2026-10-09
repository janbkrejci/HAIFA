<script setup lang="ts">
import { diffLines } from '@/lib/review'
defineProps<{ patch?: string | null; content?: string | null; binary?: boolean }>()
</script>
<template>
  <p v-if="binary" data-test="binary">binární soubor</p>
  <pre v-else-if="patch" class="patch"><span v-for="(line, i) in diffLines(patch)" :key="i" class="line" :class="line.kind" :data-kind="line.kind">{{ line.text || ' ' }}</span></pre>
  <pre v-else class="patch">{{ content ?? 'Prázdný soubor nebo změna režimu souboru' }}</pre>
</template>
<style scoped>
.patch { overflow-x: auto; padding: 8px; background: var(--panel-3); border: 1px solid var(--border-soft); border-radius: 6px; font: 13px var(--mono); }
.line { display: block; white-space: pre; }
.add { color: var(--green); background: rgba(74,222,128,.1); }
.del { color: var(--red); background: rgba(255,111,103,.1); }
.hunk { color: var(--cyan); }
.meta { color: var(--faint); }
</style>
