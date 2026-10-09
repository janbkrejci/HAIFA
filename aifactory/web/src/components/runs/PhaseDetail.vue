<script setup lang="ts">
// Port of the sssf visualizer's PhaseDetail: header, collapsible sections on the
// left (request, agent config, description, compiled prompts, gates, cost, outputs)
// and the always-visible events column on the right. Payloads arrive parsed.
import { computed, reactive, ref, watch } from 'vue'
import {
  Activity,
  AlignLeft,
  Brain,
  Check,
  Fingerprint,
  Inbox,
  MessagesSquare,
  Package,
  Receipt,
  ShieldCheck,
  SlidersHorizontal,
  SquareTerminal,
  X,
} from 'lucide-vue-next'
import {
  EVENT_TYPE_CLASS,
  eventLabel,
  eventOk,
  isPhaseHeaderLog,
  parseAgentEnd,
  parseAgentStart,
  parseQualityCall,
  parseToolCall,
} from '@/lib/events'
import { fmtClock, fmtInt, fmtMoney4, plural, secondsBetween } from '@/lib/format'
import { highlightValue } from '@/lib/highlight'
import { modelIcon, modelName } from '@/lib/models'
import {
  REQUEST_PREVIEW_CHARS,
  checksLabel,
  excerpt,
  fetchPhasePrompts,
  slotWaitLabel,
  type AgentStartPayload,
  type GateResult,
  type PhasePrompts,
  type PhaseRow,
  type TraceEnvelope,
  type TraceEvent,
  type UsageBreakdown,
} from '@/lib/runs'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import DetailSection from './DetailSection.vue'
import StatChip from './StatChip.vue'
import StatusChip from './StatusChip.vue'

const props = defineProps<{
  runId: string
  phase: PhaseRow
  /** The run's request (session.request), shown as markdown. */
  request: string | null
  gates: GateResult[]
  envelopes: TraceEnvelope[]
  events: TraceEvent[]
  /** The run's events are still on their way. */
  eventsLoading?: boolean
}>()

defineEmits<{ close: [] }>()

const phaseEvents = computed(() => [...props.events].sort((a, b) => a.rowid - b.rowid))

// The events column skips the log that only repeats the phase header.
const listedEvents = computed(() => phaseEvents.value.filter((e) => !isPhaseHeaderLog(e)))

const phaseGates = computed(() =>
  [...props.gates].sort((a, b) => (a.attempt ?? 0) - (b.attempt ?? 0) || a.id - b.id),
)

const phaseOutputs = computed(() =>
  [...props.envelopes].sort((a, b) => (a.attempt ?? 0) - (b.attempt ?? 0)),
)

const requestText = computed(() => (props.request?.trim() ? props.request : null))

// A long request starts collapsed to an excerpt ending with "…"; the button shows it whole.
const requestExpanded = ref(false)
watch(
  () => props.request,
  () => {
    requestExpanded.value = false
  },
)
const requestLong = computed(() => (requestText.value?.length ?? 0) > REQUEST_PREVIEW_CHARS)
const requestShown = computed(() => {
  const text = requestText.value ?? ''
  return requestLong.value && !requestExpanded.value ? excerpt(text, REQUEST_PREVIEW_CHARS) : text
})

const phaseDuration = computed<number | null>(() => {
  const p = props.phase
  if (p.status === 'running') return secondsBetween(p.started_at, new Date().toISOString())
  if (p.duration_s != null && Number.isFinite(p.duration_s)) return p.duration_s
  return secondsBetween(p.started_at, p.ended_at)
})

// The agent's configuration, carried on its phase's `agent_start` event; an older
// run without one still shows the harness and model of the phase row.
const agentConfig = computed<AgentStartPayload | null>(() => {
  if (props.phase.kind !== 'agent') return null
  const start = phaseEvents.value.find((e) => e.type === 'agent_start')
  const parsed = start ? parseAgentStart(start) : null
  if (parsed) return parsed
  const { harness, model } = props.phase
  if (harness == null && model == null) return null
  return { coding_agent: harness ?? undefined, model: model ?? undefined }
})

// ── Cost ───────────────────────────────────────────────────────────────────

interface UsageRow {
  key: string
  label: string
  tokens: number
  cost: number
  /** Total gets a rule above it; thinking is indented under output. */
  kind?: 'total' | 'nested'
  tip?: string
}

const USAGE_KEYS: (keyof UsageBreakdown)[] = [
  'input_tokens',
  'output_tokens',
  'cache_read_tokens',
  'cache_write_tokens',
  'reasoning_tokens',
  'total_tokens',
  'input_cost',
  'output_cost',
  'cache_read_cost',
  'cache_write_cost',
  'total_cost',
]

function hasBreakdown(u: Partial<UsageBreakdown> | null | undefined): u is Partial<UsageBreakdown> {
  return !!u && USAGE_KEYS.some((k) => typeof u[k] === 'number')
}

const THINKING_TIP = 'Thinking tokeny – součást výstupu výše, účtované za cenu výstupu. Do součtu se nepřičítají.'

const phaseUsage = computed<{ rows: UsageRow[]; partial: boolean } | null>(() => {
  const p = props.phase
  if (p.kind !== 'agent') return null
  const endEvent = phaseEvents.value.find((e) => e.type === 'agent_end')
  const end = endEvent ? parseAgentEnd(endEvent) : null
  const u = hasBreakdown(p.usage) ? p.usage : hasBreakdown(end?.usage) ? end.usage : null
  if (!u) {
    if (!p.tokens && !p.cost && !endEvent) return null
    return {
      partial: true,
      rows: [
        {
          key: 'celkem',
          label: 'celkem',
          tokens: p.tokens || endEvent?.tokens || 0,
          cost: p.cost || end?.cost || 0,
          kind: 'total',
        },
      ],
    }
  }
  const n = (v: number | undefined) => (typeof v === 'number' ? v : 0)
  const rows: UsageRow[] = [
    { key: 'vstup', label: 'vstup', tokens: n(u.input_tokens), cost: n(u.input_cost) },
    { key: 'výstup', label: 'výstup', tokens: n(u.output_tokens), cost: n(u.output_cost) },
  ]
  const reasoning = n(u.reasoning_tokens)
  if (reasoning > 0) {
    // Thinking bills at the output rate and already sits INSIDE the output row.
    const output = n(u.output_tokens)
    rows.push({
      key: 'thinking',
      label: 'thinking',
      tokens: reasoning,
      cost: output ? (n(u.output_cost) * reasoning) / output : 0,
      kind: 'nested',
      tip: THINKING_TIP,
    })
  }
  rows.push(
    { key: 'cache-cteni', label: 'cache čtení', tokens: n(u.cache_read_tokens), cost: n(u.cache_read_cost) },
    { key: 'cache-zapis', label: 'cache zápis', tokens: n(u.cache_write_tokens), cost: n(u.cache_write_cost) },
  )
  const sumTokens =
    n(u.input_tokens) + n(u.output_tokens) + n(u.cache_read_tokens) + n(u.cache_write_tokens)
  const sumCost = n(u.input_cost) + n(u.output_cost) + n(u.cache_read_cost) + n(u.cache_write_cost)
  rows.push({
    key: 'celkem',
    label: 'celkem',
    tokens: typeof u.total_tokens === 'number' ? u.total_tokens : sumTokens || p.tokens,
    cost: typeof u.total_cost === 'number' ? u.total_cost : sumCost || p.cost,
    kind: 'total',
  })
  return { rows, partial: false }
})

// ── Gates ──────────────────────────────────────────────────────────────────

const openGates = reactive(new Set<number>())

function toggleGate(id: number) {
  if (openGates.has(id)) openGates.delete(id)
  else openGates.add(id)
}

// ── Events ─────────────────────────────────────────────────────────────────

function eventDuration(e: TraceEvent): number | null {
  const s = secondsBetween(e.started_at, e.ended_at)
  if (s != null) return s
  // Tool calls without ended_at carry the coding agent's own duration_ms.
  const call = parseToolCall(e)
  if (e.type === 'tool_call' && call?.duration_ms != null) return call.duration_ms / 1000
  return null
}

const expanded = reactive(new Set<string>())

function toggleEvent(id: string) {
  if (expanded.has(id)) expanded.delete(id)
  else expanded.add(id)
}

// ── Sections ───────────────────────────────────────────────────────────────
// Every section starts closed. Only a different phase_id resets them: live
// updates replace the phase object and arrays, which must not touch this state.

const openSections = reactive(new Set<string>())
const openPrompts = reactive(new Set<string>())

function toggleSection(id: string) {
  if (openSections.has(id)) openSections.delete(id)
  else openSections.add(id)
}

function togglePrompt(id: string) {
  if (openPrompts.has(id)) openPrompts.delete(id)
  else openPrompts.add(id)
}

watch(
  () => props.phase.phase_id,
  () => {
    openSections.clear()
    openGates.clear()
    openPrompts.clear()
    expanded.clear()
  },
)

// ── Compiled prompts ───────────────────────────────────────────────────────
// Fetched once per run:phase key (no polling); a failure is not cached.

const prompts = ref<PhasePrompts | null>(null)
const promptsState = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
const promptCache = new Map<string, PhasePrompts>()
let promptKey: string | null | undefined

watch(
  () => [props.runId, props.phase.phase_id, props.phase.kind] as const,
  async ([runId, phaseId, kind]) => {
    const key = kind === 'agent' ? `${runId}:${phaseId}` : null
    if (key === promptKey) return
    promptKey = key
    if (key === null) {
      prompts.value = null
      promptsState.value = 'idle'
      return
    }
    const cached = promptCache.get(key)
    if (cached) {
      prompts.value = cached
      promptsState.value = 'ready'
      return
    }
    prompts.value = null
    promptsState.value = 'loading'
    try {
      const result = await fetchPhasePrompts(runId, phaseId)
      promptCache.set(key, result)
      if (promptKey !== key) return
      prompts.value = result
      promptsState.value = 'ready'
    } catch {
      if (promptKey === key) promptsState.value = 'error'
    }
  },
  { immediate: true },
)

interface PromptPanel {
  id: 'system' | 'user'
  title: string
  text: string
  lines: number
  truncated: boolean
}

const promptPanels = computed<PromptPanel[]>(() => {
  const p = prompts.value
  if (!p) return []
  const panels: PromptPanel[] = []
  for (const [id, title] of [
    ['system', 'system prompt'],
    ['user', 'user prompt'],
  ] as const) {
    const text = p[id]
    if (text == null) continue
    panels.push({ id, title, text, lines: text.split('\n').length, truncated: !!p.truncated?.[id] })
  }
  return panels
})

const promptsLegacy = computed(() => !!prompts.value && (prompts.value.legacy || prompts.value.source === 'agent'))
</script>

<template>
  <section class="detail phase-detail" :data-phase="phase.phase_id">
    <header class="d-head">
      <div class="d-main">
        <span class="d-name" data-test="phase-name">{{ phase.name }}</span>
        <StatusChip :status="phase.status ?? 'queued'" />
        <StatChip v-if="phaseDuration != null && Number.isFinite(phaseDuration)" kind="runtime" :value="phaseDuration" />
      </div>
      <div class="d-tags">
        <span class="tag" data-test="tag-agent">
          <span class="tag-k">agent</span>
          <span class="tag-v">{{ phase.owner ?? '—' }}</span>
        </span>
        <span class="tag" data-test="tag-kind">
          <span class="tag-k">druh</span>
          <span class="tag-v">{{ phase.kind ?? '—' }}</span>
        </span>
        <span class="tag" data-test="tag-attempt">
          <span class="tag-k">pokus</span>
          <span class="tag-v">{{ phase.attempt ?? 0 }}/{{ phase.retries ?? 0 }}</span>
        </span>
      </div>
      <button type="button" class="close" aria-label="Zavřít" data-test="phase-close" @click="$emit('close')">
        <X :size="18" :stroke-width="2" />
      </button>
    </header>

    <div
      v-if="phase.status === 'running' && phase.slot_wait"
      class="d-slot-wait"
      data-test="phase-slot-wait"
    >
      {{ slotWaitLabel(phase.slot_wait) }}
    </div>

    <div v-if="phase.error" class="error-bar d-error" data-test="phase-error">{{ phase.error }}</div>

    <div class="d-grid">
      <div class="d-col">
        <DetailSection
          v-if="requestText"
          id="request"
          title="Požadavek"
          :icon="Inbox"
          :open="openSections.has('request')"
          @toggle="toggleSection('request')"
        >
          <MarkdownView :source="requestShown" data-test="request-body" />
          <button
            v-if="requestLong"
            type="button"
            class="request-toggle"
            data-test="request-toggle"
            :aria-expanded="requestExpanded"
            @click="requestExpanded = !requestExpanded"
          >
            {{ requestExpanded ? 'Sbalit zadání' : 'Zobrazit celé zadání' }}
          </button>
        </DetailSection>

        <DetailSection
          v-if="agentConfig"
          id="config"
          title="Konfigurace agenta"
          :icon="SlidersHorizontal"
          :open="openSections.has('config')"
          @toggle="toggleSection('config')"
        >
          <div class="cfg">
            <div v-if="agentConfig.coding_agent" class="cfg-row" data-test="cfg-coding_agent">
              <span class="cfg-k">coding agent</span>
              <span class="cfg-chip">
                <SquareTerminal class="cfg-icon" :size="18" :stroke-width="2" />
                {{ agentConfig.coding_agent }}
              </span>
            </div>
            <div v-if="agentConfig.model" class="cfg-row" data-test="cfg-model">
              <span class="cfg-k">model</span>
              <Tooltip :text="agentConfig.model">
                <span class="cfg-chip" tabindex="0">
                  <img
                    v-if="modelIcon(agentConfig.model)"
                    class="cfg-model-icon"
                    :src="modelIcon(agentConfig.model)!"
                    alt=""
                  />
                  {{ modelName(agentConfig.model) }}
                </span>
              </Tooltip>
            </div>
            <div v-if="agentConfig.thinking" class="cfg-row" data-test="cfg-thinking">
              <span class="cfg-k">thinking</span>
              <span class="cfg-chip">
                <Brain class="cfg-icon" :size="18" :stroke-width="2" />
                {{ agentConfig.thinking }}
              </span>
            </div>
            <div v-if="agentConfig.tools !== undefined" class="cfg-row" data-test="cfg-tools">
              <span class="cfg-k">tools</span>
              <span v-if="agentConfig.tools === null" class="cfg-v">všechny nástroje</span>
              <span v-else class="cfg-chips">
                <span v-for="t in agentConfig.tools" :key="t" class="cfg-chip">{{ t }}</span>
              </span>
            </div>
            <div v-if="agentConfig.harness_engineering !== undefined" class="cfg-row" data-test="cfg-harness_engineering">
              <span class="cfg-k">harness engineering</span>
              <span v-if="!agentConfig.harness_engineering?.length" class="cfg-v dim">žádné</span>
              <span v-else class="cfg-chips">
                <span v-for="h in agentConfig.harness_engineering" :key="h" class="cfg-chip">{{ h }}</span>
              </span>
            </div>
            <div v-if="agentConfig.purpose" class="cfg-row" data-test="cfg-purpose">
              <span class="cfg-k">purpose</span>
              <span class="cfg-v">{{ agentConfig.purpose }}</span>
            </div>
            <div v-if="agentConfig.session_id" class="cfg-row" data-test="cfg-session">
              <span class="cfg-k">session</span>
              <span class="cfg-chip">
                <Fingerprint class="cfg-icon" :size="18" :stroke-width="2" />
                {{ agentConfig.session_id }}
              </span>
            </div>
          </div>
        </DetailSection>

        <DetailSection
          v-if="phase.description"
          id="description"
          title="Popis"
          :icon="AlignLeft"
          :open="openSections.has('description')"
          @toggle="toggleSection('description')"
        >
          <p class="d-desc">{{ phase.description }}</p>
        </DetailSection>

        <DetailSection
          v-if="phase.kind === 'agent'"
          id="prompts"
          title="Sestavené prompty"
          :icon="MessagesSquare"
          :count="promptsState === 'ready' ? promptPanels.length : null"
          :open="openSections.has('prompts')"
          @toggle="toggleSection('prompts')"
        >
          <p v-if="promptsState === 'loading'" class="faint" data-test="prompts-loading">Načítám prompty…</p>
          <p v-else-if="promptsState === 'error'" class="faint" data-test="prompts-error">
            Prompty se nepodařilo načíst.
          </p>
          <template v-else-if="promptsState === 'ready'">
            <p v-if="promptsLegacy" class="faint prompts-note" data-test="prompts-legacy">
              Běh nemá prompty jednotlivých fází – zobrazuji poslední prompty agenta.
            </p>
            <p v-if="!promptPanels.length" class="faint" data-test="prompts-empty">Žádné sestavené prompty.</p>
            <div
              v-for="panel in promptPanels"
              :key="panel.id"
              class="prompt-panel"
              data-test="prompt-panel"
              :data-prompt="panel.id"
            >
              <button
                type="button"
                class="prompt-head"
                data-test="prompt-toggle"
                :aria-expanded="openPrompts.has(panel.id)"
                @click="togglePrompt(panel.id)"
              >
                <span class="chev">{{ openPrompts.has(panel.id) ? '▾' : '▸' }}</span>
                <span class="prompt-title">{{ panel.title }}</span>
                <span class="dim" data-test="prompt-lines">
                  {{ panel.lines }} {{ plural(panel.lines, 'řádek', 'řádky', 'řádků') }}
                </span>
              </button>
              <div v-if="openPrompts.has(panel.id)" class="prompt-body">
                <p v-if="panel.truncated" class="faint prompts-note" data-test="prompt-truncated">
                  Zkráceno na {{ prompts?.max_bytes }} B.
                </p>
                <MarkdownView :source="panel.text" />
              </div>
            </div>
          </template>
        </DetailSection>

        <DetailSection
          id="gates"
          title="Gates"
          :icon="ShieldCheck"
          :count="phaseGates.length"
          :open="openSections.has('gates')"
          @toggle="toggleSection('gates')"
        >
          <p v-if="!phaseGates.length" class="faint">Žádné gates.</p>
          <div
            v-for="g in phaseGates"
            :key="g.id"
            class="gate"
            :class="g.passed ? 'pass' : 'fail'"
            data-test="gate"
            :data-gate-id="g.id"
          >
            <button
              type="button"
              class="gate-line gate-toggle"
              data-test="gate-toggle"
              :aria-expanded="openGates.has(g.id)"
              @click="toggleGate(g.id)"
            >
              <span class="chev">{{ openGates.has(g.id) ? '▾' : '▸' }}</span>
              <span class="gate-mark">
                <Check v-if="g.passed" :size="18" :stroke-width="2.5" />
                <X v-else :size="18" :stroke-width="2.5" />
              </span>
              <span class="gate-name">{{ g.gate }}</span>
              <span class="gate-verdict">{{ g.passed ? 'prošel' : 'neprošel' }}</span>
              <span v-if="g.checks" class="tag" :class="{ 'tag-fail': !g.passed }" data-test="gate-checks-label">
                <span class="tag-k">kontroly</span>
                <span class="tag-v">{{ checksLabel(g.checks) }}</span>
              </span>
              <span class="tag" data-test="gate-attempt">
                <span class="tag-k">pokus</span>
                <span class="tag-v">{{ g.attempt ?? 0 }}</span>
              </span>
              <span class="dim gate-time">{{ fmtClock(g.created_at) }}</span>
            </button>
            <div v-if="openGates.has(g.id)" class="gate-checks" data-test="gate-body">
              <p v-if="g.checks && !g.checks.length" class="faint">
                Nic ke kontrole – gate neprověřil žádnou položku.
              </p>
              <div
                v-for="(c, i) in g.checks ?? []"
                :key="i"
                class="gate-check"
                :class="c.ok ? 'pass' : 'fail'"
                data-test="gate-check"
              >
                <span class="check-mark">
                  <Check v-if="c.ok" :size="16" :stroke-width="2.5" />
                  <X v-else :size="16" :stroke-width="2.5" />
                </span>
                <span class="check-item">{{ c.item }}</span>
                <!-- Multi-line evidence (e.g. "exit 1" + output tail) gets a block. -->
                <span v-if="c.note && !c.note.includes('\n')" class="check-note dim">{{ c.note }}</span>
                <pre v-else-if="c.note" class="check-note-block">{{ c.note }}</pre>
              </div>
              <ul v-if="g.violations.length" class="violations" data-test="violations">
                <li v-for="(v, i) in g.violations" :key="i">{{ v }}</li>
              </ul>
              <p v-if="!g.checks && !g.violations.length" class="faint">Bez podrobností.</p>
            </div>
          </div>
        </DetailSection>

        <DetailSection
          v-if="phaseUsage"
          id="cost"
          title="Náklady"
          :icon="Receipt"
          :open="openSections.has('cost')"
          @toggle="toggleSection('cost')"
        >
          <table class="usage">
            <thead>
              <tr>
                <th class="u-k"></th>
                <th class="u-n">tokeny</th>
                <th class="u-c">cena</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in phaseUsage.rows"
                :key="r.key"
                :class="r.kind ? `u-${r.kind}` : undefined"
                :data-row="r.key"
              >
                <td class="u-k">
                  <Tooltip v-if="r.tip" :text="r.tip">
                    <span tabindex="0">{{ r.label }}</span>
                  </Tooltip>
                  <template v-else>{{ r.label }}</template>
                </td>
                <td class="u-n">{{ fmtInt(r.tokens) }}</td>
                <td class="u-c">{{ fmtMoney4(r.cost) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-if="phaseUsage.partial" class="faint u-note" data-test="cost-partial">
            Běh nemá rozpis po složkách – zaznamenán jen součet.
          </p>
        </DetailSection>

        <DetailSection
          id="outputs"
          title="Výstupy"
          :icon="Package"
          :count="phaseOutputs.length"
          :open="openSections.has('outputs')"
          @toggle="toggleSection('outputs')"
        >
          <p v-if="!phaseOutputs.length" class="faint">Žádné výstupy.</p>
          <div v-for="env in phaseOutputs" :key="env.envelope_id" class="output" data-test="envelope">
            <div class="output-line">
              <span class="output-type">{{ env.output_type ?? '—' }}</span>
              <span class="tag">
                <span class="tag-k">agent</span>
                <span class="tag-v">{{ env.agent ?? '—' }}</span>
              </span>
              <span class="tag">
                <span class="tag-k">pokus</span>
                <span class="tag-v">{{ env.attempt ?? 0 }}</span>
              </span>
              <span class="output-valid" :class="env.valid ? 'pass' : 'fail'">
                {{ env.valid ? 'platný' : 'neplatný' }}
              </span>
            </div>
            <!-- Safe: highlightValue escapes ALL input before emitting its own spans. -->
            <pre v-html="highlightValue(env.payload ?? env.payload_raw)" />
          </div>
        </DetailSection>
      </div>

      <div class="d-col" data-test="events-col">
        <h3><Activity class="h3-icon" :size="19" :stroke-width="2" /> Události ({{ listedEvents.length }})</h3>
        <p v-if="!listedEvents.length && eventsLoading" class="faint" data-test="phase-events-loading">Načítám události…</p>
        <p v-else-if="!listedEvents.length" class="faint">Žádné události.</p>
        <div v-for="e in listedEvents" :key="e.event_id" class="event" :data-event="e.event_id" :data-type="e.type">
          <button
            type="button"
            class="event-row"
            :class="{ open: expanded.has(e.event_id) }"
            data-test="event-toggle"
            :aria-expanded="expanded.has(e.event_id)"
            @click="toggleEvent(e.event_id)"
          >
            <span class="e-time dim">{{ fmtClock(e.started_at) }}</span>
            <span class="e-type" :class="EVENT_TYPE_CLASS[e.type ?? '']">{{ e.type }}</span>
            <span class="e-name" :class="{ 't-red': !eventOk(e) }">{{ eventLabel(e) }}</span>
            <span class="e-extra">
              <StatChip v-if="eventDuration(e) != null" kind="runtime" compact :value="eventDuration(e)" />
              <StatChip v-if="e.tokens" kind="tokens" compact :value="e.tokens" />
            </span>
          </button>

          <div v-if="expanded.has(e.event_id)" class="payload-panel" data-test="event-body">
            <template v-if="parseToolCall(e)">
              <div class="p-meta">
                <span class="p-tool">{{ parseToolCall(e)?.tool }}</span>
                <span v-if="parseToolCall(e)?.ok === false" class="t-red">chyba</span>
                <StatChip v-if="eventDuration(e) != null" kind="runtime" compact :value="eventDuration(e)" />
              </div>
              <h4>argumenty</h4>
              <!-- Safe: highlightValue escapes ALL input. -->
              <pre class="p-pre" v-html="highlightValue(parseToolCall(e)?.args ?? {})" />
              <template v-if="parseToolCall(e)?.result_snippet">
                <h4>výsledek</h4>
                <pre class="p-pre">{{ parseToolCall(e)?.result_snippet }}</pre>
              </template>
            </template>
            <template v-else-if="parseQualityCall(e)">
              <div class="p-meta quality-meta" data-test="quality-meta">
                <span><span class="dim">příkaz</span> <code>{{ parseQualityCall(e)?.command }}</code></span>
                <span>
                  <span class="dim">návratový kód</span>
                  <span
                    data-test="quality-returncode"
                    :class="{ 't-red': (parseQualityCall(e)?.returncode ?? 0) !== 0 }"
                  >{{ parseQualityCall(e)?.returncode ?? '—' }}</span>
                </span>
                <span :class="eventOk(e) ? 't-green' : 't-red'">{{ eventOk(e) ? 'prošel' : 'neprošel' }}</span>
              </div>
              <h4>payload</h4>
              <pre class="p-pre" v-html="highlightValue(e.payload)" />
            </template>
            <template v-else-if="e.payload != null">
              <h4>payload</h4>
              <pre class="p-pre" v-html="highlightValue(e.payload)" />
            </template>
            <p v-else class="faint">Bez payloadu.</p>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.detail {
  border: 1px solid var(--border-soft);
  border-radius: 16px;
  background: var(--surface);
}

.d-head {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--panel-2);
  border-radius: 16px 16px 0 0;
}

.d-main {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-wrap: wrap;
}

.d-name {
  font-size: 20px;
  font-weight: 700;
}

.d-tags {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-left: auto;
}

.tag {
  display: inline-flex;
  align-items: baseline;
  gap: 7px;
  padding: 2px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: var(--panel-3);
  font-size: 16px;
  white-space: nowrap;
}

.tag-k {
  color: var(--faint);
}

.tag-v {
  color: var(--text);
}

.close {
  display: inline-flex;
  align-items: center;
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--dim);
  cursor: pointer;
  padding: 3px 10px;
}

.close:hover {
  color: var(--text);
  border-color: var(--dim);
}

.d-desc {
  margin: 0;
  color: var(--dim);
}

/* ── agent config ── */

.cfg {
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.cfg-row {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.cfg-k {
  flex: none;
  width: 160px;
  color: var(--faint);
}

.cfg-v {
  color: var(--text);
  min-width: 0;
  overflow-wrap: anywhere;
}

.cfg-model-icon {
  width: 17px;
  height: 17px;
  flex: none;
  object-fit: contain;
}

.cfg-chips {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 6px;
}

.cfg-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 2px 12px;
  border: 1px solid var(--border-soft);
  border-radius: 999px;
  background: rgba(19, 26, 38, 0.6);
  font-family: var(--mono);
  font-size: 16px;
  overflow-wrap: anywhere;
}

/* The dark base above is a panel tint, not a neutral: light mode needs its own. */
[data-theme='light'] .cfg-chip {
  background: rgba(255, 255, 255, 0.7);
}

.cfg-icon {
  flex: none;
  color: var(--faint);
}

.d-error {
  margin: 14px 18px 0;
}

.d-slot-wait {
  margin: 14px 18px 0;
  padding: 8px 12px;
  border: 1px dashed rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  color: var(--amber);
  background: rgba(232, 182, 74, 0.08);
}

.d-grid {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
  gap: 28px;
  padding: 16px 18px 20px;
}

@media (max-width: 1100px) {
  .d-grid {
    grid-template-columns: 1fr;
  }
}

h3 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 0 0 10px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border-soft);
  font-size: 16px;
  font-weight: 700;
  color: var(--dim);
  letter-spacing: 0.05em;
}

.h3-icon {
  flex: none;
  color: var(--faint);
}

.request-toggle {
  margin-top: 8px;
  padding: 4px 10px;
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  background: var(--panel-3);
  color: var(--text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.request-toggle:hover {
  background: var(--panel-2);
}

/* ── compiled prompts ── */

.prompts-note {
  margin: 0 0 10px;
}

.prompt-panel {
  margin-bottom: 10px;
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  background: var(--panel-3);
  overflow: hidden;
}

.prompt-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  width: 100%;
  padding: 9px 14px;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-size: 16px;
  cursor: pointer;
  text-align: left;
}

.prompt-head:hover {
  background: var(--panel-2);
}

.chev {
  color: var(--faint);
  flex: none;
}

.prompt-title {
  font-weight: 700;
}

.prompt-head .dim {
  margin-left: auto;
}

.prompt-body {
  padding: 12px 14px 14px;
  border-top: 1px solid var(--border-soft);
  max-height: 60vh;
  overflow: auto;
}

/* ── gates ── */

.gate {
  margin-bottom: 10px;
  padding: 10px 14px;
  border: 1px solid var(--border-soft);
  border-left-width: 3px;
  border-radius: 8px;
  background: var(--panel-3);
}

.gate.pass {
  border-left-color: var(--green);
}

.gate.fail {
  border-left-color: var(--red);
}

.gate-line {
  display: flex;
  gap: 12px;
  align-items: baseline;
  flex-wrap: wrap;
}

.gate-toggle {
  width: 100%;
  padding: 0;
  background: none;
  border: none;
  color: var(--text);
  font: inherit;
  font-size: 16px;
  cursor: pointer;
  text-align: left;
}

.gate-mark {
  display: inline-flex;
  align-self: center;
}

.gate.pass .gate-mark,
.gate.pass .gate-verdict {
  color: var(--green);
}

.gate.fail .gate-mark,
.gate.fail .gate-verdict {
  color: var(--red);
}

.gate-name {
  color: var(--text);
  font-weight: 700;
}

.gate-time {
  margin-left: auto;
}

.gate-checks {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid var(--border-soft);
}

.gate-checks .check-item {
  font-family: var(--mono);
}

.gate-check {
  display: flex;
  gap: 10px;
  align-items: baseline;
  flex-wrap: wrap;
  padding: 3px 0;
}

.check-mark {
  display: inline-flex;
  align-self: center;
}

.gate-check.pass .check-mark {
  color: var(--green);
}

.gate-check.fail .check-mark {
  color: var(--red);
}

.check-item {
  overflow-wrap: anywhere;
  min-width: 0;
}

.check-note {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.check-note-block {
  flex-basis: 100%;
  margin: 4px 0 6px 26px;
  max-height: 30vh;
  overflow: auto;
}

.tag-fail {
  border-color: rgba(255, 111, 103, 0.55);
}

.tag-fail .tag-v {
  color: var(--red);
}

.violations {
  margin: 8px 0 2px;
  padding-left: 24px;
  color: var(--red);
}

/* ── cost ── */

.usage {
  width: 100%;
  max-width: 420px;
  border-collapse: collapse;
  font-size: 16px;
}

.usage th {
  padding: 0 0 6px;
  font-size: 14px;
  font-weight: 400;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--faint);
  border-bottom: 1px solid var(--border-soft);
}

.usage td {
  padding: 5px 0;
}

.usage .u-k {
  text-align: left;
  color: var(--dim);
}

.usage .u-n,
.usage .u-c {
  text-align: right;
  font-family: var(--mono);
  font-variant-numeric: tabular-nums;
  color: var(--text);
}

.usage .u-c {
  color: var(--green);
}

/* Thinking sits inside output: indented and muted so the column still sums. */
.u-nested .u-k {
  padding-left: 18px;
  color: var(--faint);
}

.usage .u-nested .u-n,
.usage .u-nested .u-c {
  color: var(--faint);
}

.u-total td {
  padding-top: 8px;
  border-top: 1px solid var(--border-soft);
  font-weight: 700;
}

.usage .u-total .u-k {
  color: var(--text);
}

.u-note {
  margin: 10px 0 0;
  font-size: 15px;
}

/* ── outputs ── */

.output {
  margin-bottom: 14px;
}

.output-line {
  display: flex;
  gap: 12px;
  align-items: baseline;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.output-type {
  color: var(--purple);
  font-weight: 700;
}

.output-valid.pass {
  color: var(--green);
}

.output-valid.fail {
  color: var(--red);
}

.output pre {
  max-height: 40vh;
  overflow: auto;
}

/* ── events ── */

.event {
  border-bottom: 1px solid var(--border-soft);
}

.event-row {
  display: flex;
  gap: 14px;
  align-items: baseline;
  width: 100%;
  padding: 7px 6px;
  background: none;
  border: none;
  border-radius: 6px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 16px;
  cursor: pointer;
  text-align: left;
}

.event-row:hover,
.event-row.open {
  background: var(--panel-2);
}

.e-time {
  flex: none;
  font-variant-numeric: tabular-nums;
}

.e-type {
  flex: none;
  width: 130px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.e-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.e-extra {
  margin-left: auto;
  flex: none;
  display: inline-flex;
  gap: 8px;
  align-self: center;
}

.payload-panel {
  margin: 6px 0 14px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-3);
}

.p-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: baseline;
  margin-bottom: 10px;
}

.p-meta code {
  font-family: var(--mono);
  overflow-wrap: anywhere;
}

.p-tool {
  color: var(--cyan);
  font-weight: 700;
  font-size: 17px;
}

.payload-panel h4 {
  margin: 14px 0 6px;
  font-size: 16px;
  font-weight: 700;
  color: var(--dim);
  letter-spacing: 0.06em;
}

.payload-panel h4:first-of-type {
  margin-top: 0;
}

/* Args and result each get their own block that scrolls in place. */
.p-pre {
  border: 1px solid var(--border-soft);
  border-radius: 8px;
  padding: 10px 12px;
  background: rgba(6, 8, 15, 0.55);
  max-height: 42vh;
  overflow: auto;
}

[data-theme='light'] .p-pre {
  background: rgba(255, 255, 255, 0.7);
}

.t-red {
  color: var(--red);
}

.t-green {
  color: var(--green);
}

.t-cyan {
  color: var(--cyan);
}

.t-purple {
  color: var(--purple);
}

.t-violet {
  color: var(--violet);
}
</style>
