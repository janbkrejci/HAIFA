<script setup lang="ts">
// An action the guide proposed: a preview of the change and the Provést button. Nothing is
// written until the user presses it; then the dashboard's own write API runs the action and
// the outcome is recorded in the thread (lib/assistant.ts).
import { computed, onMounted, ref } from 'vue'
import {
  ACTION_STATES,
  actionHref,
  actionPreview,
  actionTitle,
  dismissAction,
  executeAction,
  running,
  taskNow,
  type ProposedAction,
  type TaskNow,
} from '@/lib/assistant'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ action: ProposedAction; threadId: string }>()

const now = ref<TaskNow | null>(null)
onMounted(async () => {
  const { action } = props
  if (action.status === 'proposed' && action.task && ['edit_task', 'cancel_task', 'follow_up'].includes(action.kind)) {
    now.value = await taskNow(action.repo, action.task)
  }
})

const rows = computed(() => actionPreview(props.action, now.value))
const href = computed(() => actionHref(props.action))
const busy = computed(() => running.has(props.action.id))
const stateLabel = computed(() => {
  const status = props.action.status
  const label = status === 'proposed' ? '' : ACTION_STATES[status]
  return label.charAt(0).toUpperCase() + label.slice(1)
})
const multiline = (text: string | null) => !!text && (text.includes('\n') || text.length > 80)
</script>

<template>
  <div class="card" :class="action.status" data-test="assistant-action" :data-kind="action.kind">
    <div class="card-head">
      <strong data-test="assistant-action-title">{{ actionTitle(action) }}</strong>
      <a v-if="href" :href="href" class="faint open">otevřít</a>
    </div>
    <p v-if="action.reason" class="reason faint">{{ action.reason }}</p>
    <dl class="preview" data-test="assistant-action-preview">
      <template v-for="row in rows" :key="row.label">
        <dt>{{ row.label }}</dt>
        <dd>
          <template v-if="row.before !== null && row.before !== row.after">
            <pre v-if="multiline(row.before) || multiline(row.after)" class="before">{{ row.before }}</pre>
            <span v-else class="before">{{ row.before }}</span>
            <span class="arrow" aria-hidden="true">→</span>
          </template>
          <pre v-if="multiline(row.after)" class="after">{{ row.after }}</pre>
          <span v-else class="after">{{ row.after }}</span>
        </dd>
      </template>
    </dl>
    <div v-if="action.status === 'proposed'" class="buttons">
      <button type="button" class="primary" :disabled="busy" data-test="assistant-action-run" @click="executeAction(threadId, action)">
        <Spinner v-if="busy" /> Provést
      </button>
      <button type="button" :disabled="busy" data-test="assistant-action-dismiss" @click="dismissAction(threadId, action)">Zahodit</button>
    </div>
    <p v-else class="state" data-test="assistant-action-state">
      {{ stateLabel }}<template v-if="action.outcome?.message">: {{ action.outcome.message }}</template>
    </p>
  </div>
</template>

<style scoped>
.card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px solid var(--purple);
  border-radius: 10px;
  background: var(--panel-2);
}

.card.done {
  border-color: var(--green);
}

.card.failed {
  border-color: var(--red);
}

.card.dismissed {
  border-color: var(--border);
  opacity: 0.75;
}

.card-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.open {
  font-size: 13px;
}

.reason {
  margin: 0;
  font-size: 13px;
}

.preview {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 4px 10px;
  margin: 0;
  font-size: 13px;
}

.preview dt {
  color: var(--dim);
}

.preview dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}

.preview pre {
  margin: 0;
  max-height: 160px;
  overflow: auto;
  white-space: pre-wrap;
  font-family: var(--mono);
  font-size: 12px;
}

.before {
  color: var(--faint);
  text-decoration: line-through;
}

.arrow {
  margin: 0 6px;
  color: var(--dim);
}

.buttons {
  display: flex;
  gap: 8px;
}

.state {
  margin: 0;
  font-size: 13px;
  white-space: pre-wrap;
}

.failed .state {
  color: var(--red);
}

.faint {
  color: var(--faint);
}
</style>
