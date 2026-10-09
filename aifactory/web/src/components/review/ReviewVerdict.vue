<script setup lang="ts">
import type { ReviewVerdict } from '@/lib/review'
import { runHref } from '@/lib/router'

defineProps<{ verdict: ReviewVerdict | null }>()
</script>

<template>
  <p v-if="!verdict" class="faint" data-test="no-verdict">Review neběželo</p>
  <div v-else class="verdict" data-test="verdict">
    <p class="head">
      <strong :class="verdict.approved ? 'ok' : 'bad'" data-test="verdict-state">
        {{ verdict.approved ? 'schváleno' : 'neschváleno' }}
      </strong>
      <span class="dim"> · {{ verdict.agent ?? 'reviewer' }} · </span>
      <a :href="runHref(verdict.run_id)">běh {{ verdict.run_id }}</a>
    </p>
    <p v-if="verdict.summary" class="summary">{{ verdict.summary }}</p>
    <template v-if="verdict.blocking.length">
      <h4>Blokující</h4>
      <ul data-test="blocking">
        <li v-for="(b, i) in verdict.blocking" :key="i">{{ b }}</li>
      </ul>
    </template>
    <template v-if="verdict.findings.length">
      <h4>Požadavky</h4>
      <ul class="findings">
        <li v-for="(f, i) in verdict.findings" :key="i" data-test="finding">
          <span :class="f.met ? 'ok' : 'bad'">{{ f.met ? '✓' : '✗' }}</span>
          {{ f.requirement ?? '—' }}
          <span v-if="f.evidence" class="faint"> — {{ f.evidence }}</span>
        </li>
      </ul>
    </template>
  </div>
</template>

<style scoped>
.ok {
  color: var(--green);
}

.bad {
  color: var(--red);
}

.head {
  margin: 0 0 8px;
}

.summary {
  white-space: pre-wrap;
}

h4 {
  margin: 10px 0 4px;
  color: var(--dim);
}

ul {
  margin: 0;
  padding-left: 20px;
}

.findings {
  list-style: none;
  padding-left: 0;
}
</style>
