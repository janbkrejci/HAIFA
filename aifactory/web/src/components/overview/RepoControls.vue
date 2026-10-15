<script setup lang="ts">
// The factory state of a repo on the overview, under the header with the buttons (RepoActions):
// the outcome of the last button, the progress of a stop or pause ("dobíhá" → "Zastaveno"/
// "Pozastaveno"), its errors and the tasks per board state. The progress comes from the overview,
// which reloads every 2 s.
import { computed } from 'vue'
import type { OverviewRepo } from '@/lib/api'
import { controlErrors, controlStatus, stateClass, taskSummary } from '@/lib/overview'
import Spinner from '@/components/ui/Spinner.vue'
import { NO_FEEDBACK, type ControlFeedback } from './feedback'

const props = withDefaults(defineProps<{ repo: OverviewRepo; feedback?: ControlFeedback }>(), {
  feedback: () => NO_FEEDBACK,
})

const summary = computed(() => taskSummary(props.repo))
const status = computed(() => controlStatus(props.repo))
const errors = computed(() => controlErrors(props.repo))
const factory = computed(() => props.repo.factory ?? null)
const anything = computed(
  () =>
    status.value !== null ||
    summary.value.length > 0 ||
    errors.value.length > 0 ||
    props.feedback.message !== null ||
    props.feedback.error !== null,
)
</script>

<template>
  <div v-if="anything" class="repo-controls" data-test="factory-controls">
    <span
      v-if="status"
      class="status"
      :class="status.kind"
      data-test="factory-control-status"
      :data-kind="status.kind"
    >
      <Spinner v-if="status.kind === 'stopping' || status.kind === 'pausing'" />
      {{ status.text }}
    </span>

    <p v-if="feedback.message" class="message" data-test="factory-start-message">{{ feedback.message }}</p>
    <p v-if="feedback.error" class="error" data-test="factory-control-error">{{ feedback.error }}</p>
    <p v-for="(line, i) in errors" :key="i" class="error" data-test="factory-control-errors">{{ line }}</p>

    <div v-if="summary.length || factory" class="summary">
      <span v-if="summary.length" class="tasks" data-test="task-summary">
        <span
          v-for="item in summary"
          :key="item.state"
          class="chip state-chip"
          :class="stateClass(item.state)"
          data-test="task-summary-item"
          :data-state="item.state"
        >{{ item.label }} <b>{{ item.count }}</b></span>
      </span>
      <span v-if="factory && factory.max_parallel_runs !== null" class="slots" data-test="factory-slots">
        Sloty: {{ factory.running }}/{{ factory.max_parallel_runs }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.repo-controls {
  display: flex;
  flex-direction: column;
  gap: 6px;
}









.status {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--amber);
  font-size: 14px;
}

.status.stopped,
.status.paused {
  color: var(--dim);
}

.message {
  margin: 0;
  color: var(--dim);
  font-size: 13px;
}

.error {
  margin: 0;
  color: var(--red);
  font-size: 13px;
}

.summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 12px;
  font-size: 13px;
  color: var(--dim);
}

.tasks {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

.chip {
  padding: 1px 8px;
  border-radius: 999px;
}

.chip b {
  font-weight: 600;
}

.slots {
  color: var(--faint);
}
</style>
