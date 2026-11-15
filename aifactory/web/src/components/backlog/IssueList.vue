<script setup lang="ts">
import { t } from '@/lib/i18n'
import { backlogError } from '@/lib/backlogMessages'
import type { ApiIssue } from '@/lib/api'

defineProps<{ message: string; issues: ApiIssue[]; code?: string }>()
</script>

<template>
  <div class="issue-list" data-test="write-error" role="alert">
    <p class="message">{{ backlogError({ code, message }) }}</p>
    <ul v-if="issues.length">
      <li v-for="(issue, n) in issues" :key="n" :data-issue="issue.code">
        <code>{{ issue.code }}</code>: {{ backlogError(issue) }}
        <span v-if="issue.path" class="faint">({{ issue.path }})</span>
      </li>
    </ul>
    <details v-if="(code && backlogError({ code, message }) !== message) || issues.some(issue => backlogError(issue) !== issue.message)" data-test="error-details">
      <summary>{{ t('dashboard.diagnostics') }}</summary>
      <p>{{ message }}</p>
      <ul v-if="issues.length">
        <li v-for="(issue, n) in issues" :key="n"><code>{{ issue.code }}</code>: {{ issue.message }}</li>
      </ul>
    </details>
  </div>
</template>

<style scoped>
.issue-list {
  margin-top: 12px;
  padding: 10px 14px;
  border: 1px solid rgba(255, 111, 103, 0.45);
  border-radius: 8px;
  background: rgba(255, 111, 103, 0.08);
  color: var(--red);
}

.message {
  margin: 0;
  font-weight: 600;
}

ul {
  margin: 6px 0 0;
  padding-left: 20px;
  color: var(--text);
}
</style>
