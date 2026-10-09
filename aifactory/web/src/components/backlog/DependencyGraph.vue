<script setup lang="ts">
// The dependency graph of a project or step: tasks as nodes (coloured by board state),
// `depends_on` as arrows. A task node links to its detail.
import { computed, ref } from 'vue'
import {
  BOARD_STATES,
  STATE_LABELS,
  levelLabel,
  levelNoun,
  type ContainerGraph,
  type GraphNode,
} from '@/lib/backlog'
import { useLevels, useNames } from '@/lib/names'
import { NODE_HEIGHT, NODE_WIDTH, edgePath, layoutGraph } from '@/lib/graph'
import { taskHref } from '@/lib/router'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ graph: ContainerGraph }>()

const layout = computed(() =>
  layoutGraph(
    Array.isArray(props.graph.nodes) ? props.graph.nodes : [],
    Array.isArray(props.graph.edges) ? props.graph.edges : [],
  ),
)

function stateClass(node: GraphNode): string {
  return node.board_state ? `state-${node.board_state.replace(/\s+/g, '-')}` : 'state-other'
}

function stateText(node: GraphNode): string {
  if (node.board_state) return STATE_LABELS[node.board_state] ?? node.board_state
  return node.state ?? ''
}

const { names } = useNames()
const { containers } = useLevels()

/** The node's title, live from the shared names when known. */
function nodeTitle(node: GraphNode): string | null {
  return names.value[node.id]?.title ?? node.title
}

/** Level of a node: from the shared names, else task for task nodes. */
function nodeLevel(node: GraphNode): string | null {
  return names.value[node.id]?.level ?? (node.kind === 'task' ? 'task' : null)
}

/** Tooltip and accessible name: `<úroveň> <kód> <název> (<stav>)`. */
function nodeLabel(node: GraphNode): string {
  const level = nodeLevel(node)
  const head = `${node.id} ${nodeTitle(node) ?? ''} (${stateText(node)})`
  return level ? `${levelLabel(level)} ${head}` : head
}

const outsideLabel = computed(() => `mimo ${containers.value.map((l) => levelNoun(l)).join('/')}`)

// One controlled tooltip for the whole graph; it lives outside the <svg> and the
// scroll container, positioned next to the hovered/focused node.
const tip = ref<{ el: Element; text: string } | null>(null)

function showTip(e: Event, node: GraphNode) {
  const el = e.currentTarget
  if (el instanceof Element) tip.value = { el, text: nodeLabel(node) }
}

function hideTip() {
  tip.value = null
}

function clip(text: string | null, max = 24): string {
  if (!text) return ''
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
</script>

<template>
  <div class="dependency-graph" data-test="graph">
    <p v-if="!layout.nodes.length" class="faint" data-test="empty-graph">Žádné tasky</p>
    <div v-else class="canvas">
      <svg
        :width="layout.width"
        :height="layout.height"
        :viewBox="`0 0 ${layout.width} ${layout.height}`"
        role="img"
        aria-label="Graf závislostí"
      >
        <defs>
          <marker
            id="dep-arrow"
            viewBox="0 0 10 10"
            refX="10"
            refY="5"
            markerWidth="8"
            markerHeight="8"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" class="arrow" />
          </marker>
        </defs>
        <path
          v-for="edge in layout.edges"
          :key="`${edge.from}->${edge.to}`"
          class="edge"
          :data-edge="`${edge.from}->${edge.to}`"
          :d="edgePath(edge.points)"
          marker-end="url(#dep-arrow)"
        />
        <template v-for="node in layout.nodes" :key="node.id">
          <a
            v-if="node.kind === 'task'"
            :href="taskHref(node.id)"
            data-test="graph-node"
            :data-node="node.id"
            :aria-label="nodeLabel(node)"
            @mouseenter="showTip($event, node)"
            @mouseleave="hideTip"
            @focus="showTip($event, node)"
            @blur="hideTip"
          >
            <g class="node" :class="[stateClass(node), { external: node.external }]" :transform="`translate(${node.x},${node.y})`">
              <rect :width="NODE_WIDTH" :height="NODE_HEIGHT" rx="8" />
              <text x="10" y="18" class="node-id">{{ node.id }}</text>
              <text x="10" y="35" class="node-title">{{ clip(nodeTitle(node)) }}</text>
              <text :x="NODE_WIDTH - 8" y="18" class="node-state" text-anchor="end">
                {{ stateText(node) }}
              </text>
            </g>
          </a>
          <g
            v-else
            data-test="graph-node"
            :data-node="node.id"
            class="node state-other external"
            :transform="`translate(${node.x},${node.y})`"
            tabindex="0"
            :aria-label="nodeLabel(node)"
            @mouseenter="showTip($event, node)"
            @mouseleave="hideTip"
            @focus="showTip($event, node)"
            @blur="hideTip"
          >
            <rect :width="NODE_WIDTH" :height="NODE_HEIGHT" rx="8" />
            <text x="10" y="18" class="node-id">{{ node.id }}</text>
            <text x="10" y="35" class="node-title">{{ clip(nodeTitle(node)) }}</text>
            <text :x="NODE_WIDTH - 8" y="18" class="node-state" text-anchor="end">
              {{ stateText(node) }}
            </text>
          </g>
        </template>
      </svg>
    </div>
    <Tooltip :text="tip?.text ?? ''" :anchor="tip?.el ?? null" />
    <ul class="legend" data-test="legend">
      <li v-for="state in BOARD_STATES" :key="state" :class="`state-${state.replace(/\s+/g, '-')}`">
        <span class="swatch" />{{ STATE_LABELS[state] }}
      </li>
      <li class="external-key" data-test="outside-key"><span class="swatch" />{{ outsideLabel }}</li>
    </ul>
  </div>
</template>

<style scoped>
.dependency-graph {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.canvas {
  overflow: auto;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

svg {
  display: block;
}

.edge {
  fill: none;
  stroke: var(--faint);
  stroke-width: 1.5;
}

.arrow {
  fill: var(--faint);
}

.node rect {
  fill: var(--panel);
  stroke: var(--border);
  stroke-width: 1.5;
}

.node text {
  fill: var(--text);
  font-size: 13px;
}

.node .node-id {
  font-family: var(--mono);
  fill: var(--dim);
  font-size: 12px;
}

.node .node-state {
  font-size: 11px;
}

a:hover .node rect {
  stroke-width: 2.5;
}

.node.external rect {
  stroke-dasharray: 5 4;
}

.state-todo rect {
  stroke-dasharray: 3 3;
}

.state-ready rect {
  stroke: var(--cyan);
}

.state-ready .node-state {
  fill: var(--cyan);
}

.state-blocked rect {
  stroke: var(--amber);
}

.state-blocked .node-state {
  fill: var(--amber);
}

.state-running rect {
  stroke: var(--blue);
}

.state-running .node-state {
  fill: var(--blue);
}

.state-in-review rect {
  stroke: var(--purple);
}

.state-in-review .node-state {
  fill: var(--purple);
}

.state-done rect {
  stroke: var(--green);
}

.state-done .node-state {
  fill: var(--green);
}

.state-cancelled text {
  fill: var(--faint);
  text-decoration: line-through;
}

.state-other .node-state {
  fill: var(--faint);
}

.legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  list-style: none;
  margin: 0;
  padding: 0;
  font-size: 13px;
  color: var(--dim);
}

.legend li {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.swatch {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 1.5px solid var(--border);
  border-radius: 3px;
}

.legend .state-ready .swatch {
  border-color: var(--cyan);
}

.legend .state-blocked .swatch {
  border-color: var(--amber);
}

.legend .state-running .swatch {
  border-color: var(--blue);
}

.legend .state-in-review .swatch {
  border-color: var(--purple);
}

.legend .state-done .swatch {
  border-color: var(--green);
}

.legend .state-todo .swatch,
.legend .external-key .swatch {
  border-style: dashed;
}
</style>
