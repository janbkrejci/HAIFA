<script setup lang="ts">
import type { CheckResult } from '@/lib/review'

defineProps<{ checks: CheckResult[] }>()
</script>

<template>
  <p v-if="!checks.length" class="faint" data-test="no-checks">Gates ani testy neběžely</p>
  <ul v-else class="checks">
    <li v-for="(c, i) in checks" :key="i" data-test="check" :class="c.passed ? 'pass' : 'fail'">
      <span class="mark">{{ c.passed ? '✓' : '✗' }}</span>
      <span class="kind">{{ c.kind === 'gate' ? 'gate' : 'test' }}</span>
      <span class="name">{{ c.name }}</span>
      <span class="dim">{{ c.phase }}</span>
      <span v-if="c.detail" class="detail faint">{{ c.detail }}</span>
    </li>
  </ul>
</template>

<style scoped>
.checks {
  list-style: none;
  margin: 0;
  padding: 0;
}

li {
  display: flex;
  gap: 10px;
  align-items: baseline;
  padding: 4px 0;
}

.mark {
  font-weight: 700;
}

.pass .mark {
  color: var(--green);
}

.fail .mark {
  color: var(--red);
}

.kind {
  color: var(--faint);
  font-size: 13px;
  text-transform: uppercase;
}

.name {
  font-family: var(--mono);
}

.detail {
  white-space: pre-wrap;
}
</style>
