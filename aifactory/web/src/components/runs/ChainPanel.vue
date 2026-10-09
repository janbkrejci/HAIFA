<script setup lang="ts">
// Auto-continue chains above the list of runs: every run with its result (state, PR, what
// auto-merge did, error), slots, tasks run alone, skipped tasks. An ended chain can be hidden.
import { reviewHref, runHref, taskHref } from '@/lib/router'
import { prStateLabel, shownState } from '@/lib/runs'
import { chainStateLabel, firstLine, skipReasonLabel, type Chain } from '@/lib/chains'
import Tooltip from '@/components/ui/Tooltip.vue'
import StatusChip from './StatusChip.vue'

withDefaults(
  defineProps<{
    chains: Chain[]
    /** The chain being hidden (its button is disabled). */
    dismissing?: string | null
  }>(),
  { dismissing: null },
)
const emit = defineEmits<{ dismiss: [chainId: string] }>()
</script>

<template>
  <section v-if="chains.length" class="chain-panel" data-test="chain-panel">
    <article v-for="chain in chains" :key="chain.chain_id" class="chain" data-test="chain">
      <header class="chain-head">
        <strong>Řetěz od <a class="mono" :href="taskHref(chain.task_id)" data-test="chain-task">{{ chain.task_id }}</a></strong>
        <span class="faint" data-test="chain-state">· {{ chainStateLabel(chain) }}</span>
        <span class="slots" data-test="chain-slots">
          Sloty: {{ chain.running }}/{{ chain.max_parallel }} (volné {{ chain.free_slots }})
        </span>
        <button
          v-if="chain.state !== 'running'"
          type="button"
          class="dismiss"
          data-test="chain-dismiss"
          :disabled="dismissing === chain.chain_id"
          @click="emit('dismiss', chain.chain_id)"
        >
          Skrýt
        </button>
      </header>
      <ul v-if="chain.runs.length" class="chain-runs">
        <li v-for="run in chain.runs" :key="run.run_id" data-test="chain-run">
          <a :href="runHref(run.run_id)" class="mono">{{ run.task_id ?? run.run_id }}</a>
          <StatusChip :status="shownState(run)" />
          <span v-if="run.workflow" class="faint" data-test="chain-run-workflow">{{ run.workflow }}</span>
          <a v-if="run.pr" :href="run.pr.url" target="_blank" rel="noopener" data-test="chain-run-pr">
            PR #{{ run.pr.pr_id }} ({{ prStateLabel(run.pr.state) }})
          </a>
          <a v-if="run.pr && run.task_id" :href="reviewHref(run.task_id)" data-test="chain-run-review">Review</a>
          <span v-if="run.pr?.merged_by === 'auto-merge'" class="merged" data-test="chain-run-merged">
            sloučil auto-merge
          </span>
          <span
            v-else-if="run.pr?.state === 'open' && run.pr.auto_merge_error"
            class="warn"
            data-test="chain-run-merge-error"
          >
            auto-merge nesloučil: {{ run.pr.auto_merge_error }}
          </span>
          <Tooltip v-if="run.error" :text="run.error">
            <span class="run-error" data-test="chain-run-error" tabindex="0">{{ firstLine(run.error) }}</span>
          </Tooltip>
        </li>
      </ul>
      <p v-if="chain.exclusive.length" class="exclusive" data-test="chain-exclusive">
        Samostatně:
        <template v-for="(id, n) in chain.exclusive" :key="id"
          ><template v-if="n">, </template><a class="mono" :href="taskHref(id)">{{ id }}</a></template
        >
      </p>
      <ul v-if="chain.skipped.length" class="chain-skips">
        <li v-for="skip in chain.skipped" :key="`${skip.task_id}-${skip.reason}`" data-test="chain-skip">
          <a class="mono" :href="taskHref(skip.task_id)" data-test="chain-skip-task">{{ skip.task_id }}</a>
          <span class="reason" :data-reason="skip.reason">{{ skipReasonLabel(skip.reason) }}</span>
          <span class="detail">{{ skip.detail }}</span>
        </li>
      </ul>
    </article>
  </section>
</template>

<style scoped>
.chain-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 18px;
}

.chain {
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.chain-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 8px;
}

.slots {
  margin-left: auto;
  color: var(--dim);
}

.dismiss {
  padding: 2px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: transparent;
  color: var(--dim);
  font: inherit;
  cursor: pointer;
}

.dismiss:hover {
  color: var(--text);
}

.dismiss:disabled {
  opacity: 0.5;
  cursor: default;
}

.merged {
  color: var(--green);
  font-size: 14px;
}

.warn {
  color: var(--amber);
  font-size: 14px;
}

.run-error {
  max-width: 48ch;
  overflow: hidden;
  color: var(--red);
  font-size: 14px;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.chain-runs,
.chain-skips {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
}

.chain-runs li,
.chain-skips li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.reason {
  padding: 1px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--amber);
  font-size: 13px;
}

.detail {
  color: var(--dim);
  font-size: 14px;
}

.exclusive {
  margin: 8px 0 0;
  color: var(--dim);
}

.faint {
  color: var(--faint);
}
</style>
