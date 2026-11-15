<script setup lang="ts">
import { t } from '@/lib/i18n'
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
    <DetailSection id="costs" :title="t('runs.naklady')" :icon="Coins" :open="open" @toggle="$emit('toggle')">
      <p v-if="error" class="error" data-test="totals-error">{{ error }}</p>
      <p v-else-if="!totals" class="faint" data-test="totals-loading">{{ t('runs.nacitam') }}</p>
      <template v-else>
        <p class="backlog" data-test="backlog-total"> {{ t('runs.cely_backlog') }} <strong data-col="cost">{{ fmtCost(totals.backlog.cost) }}</strong>
          · <span data-col="tokens">{{ fmtTokens(totals.backlog.tokens) }}</span> {{ t('runs.tokenCount', {}, totals.backlog.tokens) }} · <span data-col="runs">{{ totals.backlog.runs }}</span> {{ t('runs.runCount', {}, totals.backlog.runs) }}
          <span v-if="loading" class="faint" data-test="totals-refreshing"> {{ t('runs.obnovuji') }}</span>
        </p>
        <table v-if="totals.tasks.length" class="table">
          <thead>
            <tr>
              <th>{{ t('runs.task') }}</th>
              <th class="num">{{ t('runs.behy') }}</th>
              <th class="num">{{ t('runs.tokeny') }}</th>
              <th class="num">{{ t('runs.naklady') }}</th>
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
