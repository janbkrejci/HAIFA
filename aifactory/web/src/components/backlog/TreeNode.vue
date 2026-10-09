<script setup lang="ts">
// A row of the backlog tree. A click anywhere on a project or step row folds it (the arrow
// as well), only its Graf link opens the dependency graph and its switch button opens the
// auto-continue and auto-merge switches under the row (written to the working tree, the
// tree reloads). A click on a task row opens the task detail.
import { computed, ref } from 'vue'
import { ChevronRight, SlidersHorizontal } from 'lucide-vue-next'
import {
  BOARD_STATES,
  autoMode,
  flattenIssues,
  isExpanded,
  levelLabel,
  nodeKey,
  setAutoContinue,
  setAutoMerge,
  toggleExpanded,
  type AutoMode,
  type BacklogNode,
} from '@/lib/backlog'
import { graphHref, taskHref } from '@/lib/router'
import AutoContinueToggle from './AutoContinueToggle.vue'
import StateChip from './StateChip.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import CodeTip from '@/components/ui/CodeTip.vue'

const props = defineProps<{ node: BacklogNode; levels: string[]; depth: number }>()
const emit = defineEmits<{ changed: [] }>()

const key = computed(() => (props.node.kind === 'container' ? nodeKey(props.node) : props.node.path))
const open = computed(() => props.node.kind === 'container' && isExpanded(key.value))
// Tasks of the container per board state, every task (no filter applies), empty states left out.
const stateCounts = computed(() => {
  const counts = props.node.kind === 'container' ? (props.node.state_counts ?? {}) : {}
  return BOARD_STATES.filter((s) => (counts[s] ?? 0) > 0).map((s) => ({ state: s, count: counts[s] ?? 0 }))
})

function toggle() {
  toggleExpanded(key.value)
}

type SwitchKey = 'auto' | 'merge'
const switchesOpen = ref(false)
const pending = ref<{ key: SwitchKey; mode: AutoMode } | null>(null)
const switchError = ref<string | null>(null)
const canSwitch = computed(() => props.node.kind === 'container' && !!props.node.id && props.node.can_toggle === true)

async function setSwitch(key: SwitchKey, mode: AutoMode) {
  if (props.node.kind !== 'container' || !props.node.id) return
  pending.value = { key, mode }
  switchError.value = null
  try {
    if (key === 'auto') await setAutoContinue(props.node.id, mode)
    else await setAutoMerge(props.node.id, mode)
    emit('changed')
  } catch (e) {
    switchError.value = flattenIssues(e).message
  } finally {
    pending.value = null
  }
}

function openTask(event: MouseEvent) {
  if (props.node.kind !== 'task' || (event.target as Element | null)?.closest('a')) return
  window.location.hash = taskHref(props.node.id)
}
</script>

<template>
  <li v-if="node.kind === 'container'" class="container" :data-node="node.id ?? node.path">
    <div
      class="row head clickable"
      :style="{ paddingLeft: `${depth * 20}px` }"
      data-test="container-row"
      @click="toggle"
    >
      <button
        type="button"
        class="toggle"
        data-test="toggle"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-label="open ? 'Sbalit' : 'Rozbalit'"
        @click.stop="toggle"
      >
        <ChevronRight :size="16" class="chevron" :class="{ open }" />
      </button>
      <span class="level" data-test="level">{{ levelLabel(levels[depth] ?? node.level) }}</span>
      <CodeTip :code="node.id"><span class="id">{{ node.id ?? node.path }}</span></CodeTip>
      <span class="title">{{ node.title }}</span>
      <Tooltip v-if="node.auto_continue === true" text="auto-continue zapnuto">
        <span class="auto" data-test="auto-badge" tabindex="0">auto</span>
      </Tooltip>
      <Tooltip v-if="node.auto_merge === true" text="auto-merge zapnuto">
        <span class="auto" data-test="merge-badge" tabindex="0">merge</span>
      </Tooltip>
      <span v-if="stateCounts.length" class="states" data-test="state-counts">
        <StateChip v-for="s in stateCounts" :key="s.state" :state="s.state" :count="s.count" />
      </span>
      <a
        v-if="node.id"
        :href="graphHref(node.id)"
        class="graph-link"
        data-test="graph-link"
        @click.stop
      >Graf</a>
      <button
        v-if="canSwitch"
        type="button"
        class="switch-button"
        data-test="switches"
        :aria-expanded="switchesOpen ? 'true' : 'false'"
        aria-label="Auto-continue a auto-merge"
        @click.stop="switchesOpen = !switchesOpen"
      >
        <SlidersHorizontal :size="15" />
      </button>
    </div>
    <div
      v-if="switchesOpen && canSwitch"
      class="switches"
      :style="{ paddingLeft: `${depth * 20 + 28}px` }"
      data-test="switches-panel"
    >
      <AutoContinueToggle
        :mode="autoMode(node.auto_continue)"
        :effective="node.effective_auto_continue ?? false"
        :busy="!!pending"
        :pending="pending?.key === 'auto' ? pending.mode : null"
        @change="setSwitch('auto', $event)"
      />
      <AutoContinueToggle
        label="Auto-merge"
        test-prefix="merge"
        hint="workflow bez review se automaticky nemerguje"
        :mode="autoMode(node.auto_merge)"
        :effective="node.effective_auto_merge ?? false"
        :busy="!!pending"
        :pending="pending?.key === 'merge' ? pending.mode : null"
        @change="setSwitch('merge', $event)"
      />
      <p v-if="switchError" class="warn" data-test="switches-error">{{ switchError }}</p>
    </div>
    <ul v-if="open" data-test="children">
      <TreeNode
        v-for="child in node.children"
        :key="child.kind === 'task' ? child.path : (child.id ?? child.path)"
        :node="child"
        :levels="levels"
        :depth="depth + 1"
        @changed="emit('changed')"
      />
    </ul>
  </li>
  <li v-else class="task" :data-task="node.id">
    <div
      class="row clickable"
      :style="{ paddingLeft: `${depth * 20 + 28}px` }"
      data-test="task-row"
      @click="openTask"
    >
      <a :href="taskHref(node.id)" class="task-link">
        <span class="id">{{ node.id }}</span>
        <span class="title">{{ node.title }}</span>
      </a>
      <StateChip :state="node.board_state" :blocked-by="node.blocked_by" />
      <span v-if="node.invalid" class="warn" data-test="invalid">neplatný status</span>
      <span class="workflow" :class="{ faint: !node.workflow }">
        {{ node.workflow ?? 'bez workflow' }}
      </span>
    </div>
  </li>
</template>

<style scoped>
ul {
  list-style: none;
  margin: 0;
  padding: 0;
}

.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 6px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border-soft);
}

.head {
  font-weight: 600;
}

.clickable {
  cursor: pointer;
}

.clickable:hover {
  background: var(--panel-2);
}

.toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  margin-left: 2px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: none;
  color: var(--dim);
  cursor: pointer;
}

.toggle:hover {
  background: var(--panel-3);
  color: var(--text);
}

.chevron {
  transition: transform 0.12s ease;
}

.chevron.open {
  transform: rotate(90deg);
}

.level {
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--faint);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.id {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--dim);
}

.task-link {
  display: inline-flex;
  gap: 10px;
  color: var(--text);
  text-decoration: none;
}

.task-link:hover .title {
  text-decoration: underline;
}

.workflow {
  margin-left: auto;
  font-size: 14px;
}

.states {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
  font-weight: 400;
}

.switch-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 22px;
  padding: 0;
  border: 0;
  border-radius: 4px;
  background: none;
  color: var(--dim);
  cursor: pointer;
}

.switch-button:hover,
.switch-button[aria-expanded='true'] {
  background: var(--panel-3);
  color: var(--text);
}

.switches {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 28px;
  padding-top: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border-soft);
  background: var(--panel-2);
}

.switches .warn {
  margin: 0;
}

.graph-link {
  margin-left: auto;
  font-size: 13px;
  font-weight: 400;
  color: var(--dim);
}

.auto {
  padding: 0 6px;
  border: 1px solid rgba(90, 210, 221, 0.45);
  border-radius: 4px;
  font-size: 12px;
  font-weight: 400;
  color: var(--cyan);
}

.warn {
  color: var(--amber);
  font-size: 13px;
}
</style>
