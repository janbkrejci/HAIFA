<script setup lang="ts">
// Cost totals over every run (GET /api/runs/totals): folded by default, RunsView loads them when
// the section opens.
import { Coins } from 'lucide-vue-next'
import DetailSection from './DetailSection.vue'
import { fmtCost, fmtTokens } from '@/lib/format'
import type { RunTotals } from '@/lib/runs'

defineProps<{ open: boolean; totals: RunTotals | null; loading: boolean; error: string | null }>()
defineEmits<{ toggle: [] }>()
</script>

<template>
  <div class="totals" data-test="cost-totals">
    <DetailSection id="costs" title="Náklady" :icon="Coins" :open="open" @toggle="$emit('toggle')">
      <p v-if="error" class="error" data-test="totals-error">{{ error }}</p>
      <p v-else-if="!totals" class="faint" data-test="totals-loading">Načítám…</p>
      <template v-else>
        <p class="backlog" data-test="backlog-total">
          Celý backlog:
          <strong data-col="cost">{{ fmtCost(totals.backlog.cost) }}</strong>
          · <span data-col="tokens">{{ fmtTokens(totals.backlog.tokens) }}</span> tokenů
          · <span data-col="runs">{{ totals.backlog.runs }}</span> běhů
          <span v-if="loading" class="faint" data-test="totals-refreshing"> · obnovuji…</span>
        </p>
        <table v-if="totals.tasks.length" class="table">
          <thead>
            <tr>
              <th>Task</th>
              <th class="num">Běhy</th>
              <th class="num">Tokeny</th>
              <th class="num">Náklady</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="t in totals.tasks" :key="t.task_id" :data-task="t.task_id">
              <td data-test="task-label">
                <span class="task-id">{{ t.task_id }}</span
                ><span v-if="t.task_title" class="dim">{{ ' ' + t.task_title }}</span>
              </td>
              <td class="num">{{ t.runs }}</td>
              <td class="num">{{ fmtTokens(t.tokens) }}</td>
              <td class="num" data-col="cost">{{ fmtCost(t.cost) }}</td>
            </tr>
          </tbody>
        </table>
      </template>
    </DetailSection>
  </div>
</template>

<style scoped>
.totals {
  margin-top: 28px;
}

.error {
  margin: 0;
  color: var(--red, #e5484d);
}

.backlog {
  margin: 0 0 12px;
  color: var(--dim);
}

.backlog strong {
  color: var(--text);
  font-family: var(--mono);
}

.table {
  border-collapse: collapse;
  min-width: 50%;
}

th,
td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-soft);
  text-align: left;
}

th {
  color: var(--faint);
  font-weight: 600;
  font-size: 14px;
}

.num {
  text-align: right;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
}

.task-id {
  font-family: var(--mono);
}
</style>
