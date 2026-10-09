<script setup lang="ts">
// The run's waterfall (gantt), ported from the sssf visualizer's SessionTrace.vue.
// Layout lives in lib/waterfall.ts; this component only renders it.
import { computed, ref, type Component } from 'vue'
import { Bot, Check, Circle, LoaderCircle, SquareTerminal, UserRound, X } from 'lucide-vue-next'
import { hexAlpha } from '@/lib/events'
import { fmtDuration, fmtInt } from '@/lib/format'
import { modelIcon, modelName } from '@/lib/models'
import { runHref } from '@/lib/router'
import type { PhaseKind, PhaseRow, RunDetail, TraceEvent } from '@/lib/runs'
import {
  blockDurationMs,
  buildLanes,
  buildTimeline,
  contextFill,
  contextLabel,
  toolTicks,
  type Lane,
} from '@/lib/waterfall'
import Tooltip from '@/components/ui/Tooltip.vue'
import StatChip from './StatChip.vue'

const props = defineProps<{
  detail: RunDetail
  events: TraceEvent[]
  phaseId?: string | null
  now: number
}>()

const lanes = computed(() => buildLanes(props.detail, props.events))
const timeline = computed(() => buildTimeline(props.detail, props.now))
const hasPhases = computed(() => (props.detail.phases ?? []).length > 0)

const KIND_ICONS: Record<PhaseKind, Component> = { engineer: UserRound, code: SquareTerminal, agent: Bot }

const STATUS_GLYPH: Record<string, Component> = {
  success: Check,
  fail: X,
  failed: X,
  running: LoaderCircle,
  queued: Circle,
}

const STATUS_LABEL: Record<string, string> = {
  success: 'úspěch',
  fail: 'chyba',
  failed: 'chyba',
  running: 'běží',
  queued: 'čeká',
}

function isFail(status: string | null): boolean {
  return status === 'fail' || status === 'failed'
}

function geom(p: PhaseRow) {
  return timeline.value.blocks[p.phase_id] ?? null
}

function blockStyle(p: PhaseRow, lane: Lane): Record<string, string> | undefined {
  const g = geom(p)
  if (!g) return undefined
  return {
    left: `${g.left}%`,
    width: `${g.width}%`,
    background: `linear-gradient(180deg, ${hexAlpha(lane.color, 0.2)}, ${hexAlpha(lane.color, 0.05)})`,
    borderColor: isFail(p.status) ? 'rgba(255, 111, 103, 0.8)' : hexAlpha(lane.color, 0.55),
    '--lane-glow': hexAlpha(lane.color, 0.28),
  }
}

function durMs(p: PhaseRow): number {
  return blockDurationMs(p, props.now)
}

function blockTip(p: PhaseRow): string {
  const lines = [`${p.name ?? p.phase_id} — ${STATUS_LABEL[p.status ?? ''] ?? p.status ?? '—'}`]
  if (p.description) lines.push(p.description)
  lines.push(`Harness: ${p.harness ?? '—'} · Model: ${p.model ?? '—'}`)
  const dur = durMs(p)
  lines.push(`Pokus: ${p.attempt ?? '—'} · Doba: ${fmtDuration(Number.isFinite(dur) ? dur / 1000 : null)}`)
  return lines.join('\n')
}

function ctxTip(lane: Lane): string {
  const c = lane.context
  if (!c) return ''
  return `${fmtInt(c.used)} / ${fmtInt(c.window)} tokenů · zbývá ${fmtInt(c.window - c.used)}`
}

const tip = ref<{ el: Element | null; phase: PhaseRow | null }>({ el: null, phase: null })
const tipText = computed(() => (tip.value.phase ? blockTip(tip.value.phase) : ''))

function showTip(event: Event, p: PhaseRow) {
  tip.value = { el: event.currentTarget as Element, phase: p }
}

function hideTip() {
  tip.value = { el: null, phase: null }
}

function select(p: PhaseRow) {
  window.location.hash = runHref(props.detail.run.run_id, p.phase_id === props.phaseId ? null : p.phase_id)
}
</script>

<template>
  <p v-if="!hasPhases" class="faint">Žádné fáze v trace.</p>
  <div v-else class="waterfall" data-test="waterfall">
    <div class="row axis-row">
      <div class="label" />
      <div class="track">
        <span v-if="timeline.zonePct" class="zone-head" :style="{ width: `${timeline.zonePct}%` }">požadavek</span>
        <span v-for="(t, i) in timeline.ticks" :key="i" class="axis-label" :style="{ left: `${t.pct}%` }">{{
          t.label
        }}</span>
      </div>
    </div>

    <div
      v-for="lane in lanes"
      :key="lane.id"
      class="row lane"
      :class="`kind-${lane.kind}`"
      :data-lane="lane.id"
    >
      <div class="label">
        <span class="lane-name" :style="{ color: lane.color }" :data-color="lane.color">
          <component :is="KIND_ICONS[lane.kind]" class="lane-icon" :size="20" :stroke-width="2" />
          {{ lane.label }}
        </span>
        <Tooltip v-if="lane.model" :text="lane.model">
          <span class="lane-meta lane-model" data-test="lane-model">
            <img v-if="modelIcon(lane.model)" class="model-icon" :src="modelIcon(lane.model)!" alt="" />
            {{ modelName(lane.model) }}
          </span>
        </Tooltip>
        <Tooltip v-if="lane.context" :text="ctxTip(lane)">
          <span class="lane-ctx" data-test="lane-ctx">
            <span class="ctx-head">
              <span class="ctx-label">Kontext</span>
              <span class="ctx-pct">{{ contextLabel(lane.context) }}</span>
            </span>
            <span class="ctx-bar">
              <span
                class="ctx-fill"
                :style="{
                  width: contextFill(lane.context),
                  background: `linear-gradient(90deg, ${hexAlpha(lane.color, 0.55)}, ${lane.color})`,
                  boxShadow: `0 0 10px ${hexAlpha(lane.color, 0.45)}`,
                }"
              />
            </span>
          </span>
        </Tooltip>
        <span v-if="lane.meta" class="lane-meta">{{ lane.meta }}</span>
      </div>
      <div class="track">
        <span v-if="timeline.zonePct" class="zone-divider" :style="{ left: `${timeline.zonePct}%` }" />
        <span v-for="(t, i) in timeline.ticks" :key="i" class="gridline" :style="{ left: `${t.pct}%` }" />
        <template v-for="p in lane.phases" :key="p.phase_id">
          <button
            v-if="geom(p)"
            type="button"
            class="block"
            :class="[p.status, { selected: p.phase_id === phaseId, failed: isFail(p.status) }]"
            :style="blockStyle(p, lane)"
            :data-phase="p.phase_id"
            :data-name="p.name"
            :aria-pressed="p.phase_id === phaseId"
            @click="select(p)"
            @mouseenter="showTip($event, p)"
            @mouseleave="hideTip"
            @focus="showTip($event, p)"
            @blur="hideTip"
          >
            <span class="b-top">
              <span class="b-status" :class="p.status"
                ><component :is="STATUS_GLYPH[p.status ?? ''] ?? Circle" :size="16" :stroke-width="2.5"
              /></span>
              <span class="b-name">{{ p.name }}</span>
              <StatChip
                v-if="Number.isFinite(durMs(p))"
                class="b-dur"
                kind="runtime"
                compact
                plain
                :value="durMs(p) / 1000"
              />
            </span>
            <span class="b-desc">{{ p.description }}</span>
            <span
              v-for="(t, i) in toolTicks(p, events, now)"
              :key="i"
              class="tool-tick"
              :class="{ err: !t.ok }"
              :style="{ left: `${t.x}%` }"
            />
          </button>
        </template>
        <button
          v-for="(p, i) in lane.phases.filter((q) => !q.started_at)"
          :key="p.phase_id"
          type="button"
          class="block queued"
          :class="{ selected: p.phase_id === phaseId }"
          :style="{ right: `${10 + i * 5}px`, width: '170px' }"
          :data-phase="p.phase_id"
          :data-name="p.name"
          :aria-pressed="p.phase_id === phaseId"
          @click="select(p)"
          @mouseenter="showTip($event, p)"
          @mouseleave="hideTip"
          @focus="showTip($event, p)"
          @blur="hideTip"
        >
          <span class="b-top">
            <span class="b-status queued"><Circle :size="16" :stroke-width="2.5" /></span>
            <span class="b-name">{{ p.name }}</span>
          </span>
          <span class="b-desc">ve frontě</span>
        </button>
      </div>
    </div>
    <Tooltip :text="tipText" :anchor="tip.el" />
  </div>
</template>

<style scoped>
.waterfall {
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
  overflow: hidden;
}

.row {
  display: grid;
  grid-template-columns: 240px 1fr;
}

.axis-row {
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
}

.axis-row .track {
  height: 36px;
  overflow: hidden;
}

.zone-head {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  color: var(--amber);
  border-right: 1px solid var(--border);
}

.axis-label {
  position: absolute;
  bottom: 7px;
  transform: translateX(-50%);
  font-family: var(--mono);
  font-size: 14px;
  color: var(--dim);
  white-space: nowrap;
}

.label {
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: flex-start;
  gap: 2px;
  border-right: 1px solid var(--border);
  overflow: hidden;
  white-space: nowrap;
}

.lane-name {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
  font-size: 16px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}

.lane-icon {
  flex: none;
  opacity: 0.85;
}

.lane-meta {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--dim);
  overflow: hidden;
  text-overflow: ellipsis;
}

.lane-model {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.model-icon {
  width: 16px;
  height: 16px;
  flex: none;
  object-fit: contain;
}

.lane-ctx {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 2px;
  width: 180px;
  max-width: 100%;
}

.ctx-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.ctx-label {
  font-size: 13px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
}

.ctx-pct {
  font-family: var(--mono);
  font-size: 13px;
  color: var(--dim);
}

.ctx-bar {
  height: 6px;
  border-radius: 999px;
  background: rgba(6, 8, 15, 0.75);
  border: 1px solid var(--border-soft);
  overflow: hidden;
}

[data-theme='light'] .ctx-bar {
  background: rgba(0, 0, 0, 0.07);
}

.ctx-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  transition: width 300ms ease;
}

.lane {
  border-bottom: 1px solid var(--border-soft);
}

.lane:last-child {
  border-bottom: none;
}

.track {
  position: relative;
  height: 118px;
  overflow: hidden;
}

.zone-divider {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px solid var(--border);
}

.gridline {
  position: absolute;
  top: 0;
  bottom: 0;
  border-left: 1px dashed rgba(174, 191, 212, 0.14);
}

.block {
  position: absolute;
  top: 13px;
  height: 92px;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
  gap: 4px;
  padding: 10px 12px 16px;
  border-radius: 10px;
  border: 1px solid;
  font: inherit;
  font-size: 15px;
  color: var(--text);
  cursor: pointer;
  overflow: hidden;
  white-space: nowrap;
  text-align: left;
  transition: box-shadow 0.16s ease;
}

.block:hover {
  box-shadow: 0 0 18px var(--lane-glow, rgba(108, 182, 255, 0.2));
}

.b-top {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.b-status {
  flex: none;
  display: inline-flex;
}

.b-status.success {
  color: var(--green);
}

.b-status.fail,
.b-status.failed {
  color: var(--red);
}

.b-status.running {
  color: var(--blue);
  animation: pulse 1.2s ease-in-out infinite;
}

.b-status.queued {
  color: var(--faint);
}

.block .b-name {
  font-size: 16px;
  font-weight: 700;
  overflow: hidden;
  text-overflow: ellipsis;
}

.block .b-dur {
  margin-left: auto;
  flex: none;
}

.block .b-desc {
  color: var(--dim);
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.block.running {
  animation: pulse 1.6s ease-in-out infinite;
}

.block.queued {
  background: transparent;
  border-style: dashed;
  border-color: var(--faint);
  color: var(--dim);
}

.block.selected {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
  box-shadow: 0 0 22px var(--lane-glow, rgba(108, 182, 255, 0.25));
}

.tool-tick {
  position: absolute;
  bottom: 4px;
  width: 3px;
  height: 9px;
  background: currentColor;
  opacity: 0.55;
  border-radius: 1px;
}

.tool-tick.err {
  background: var(--red);
  opacity: 1;
}
</style>
