// Event labels, ported from the sssf visualizer's src/lib/events.ts (payloads arrive parsed).
import type {
  AgentEndPayload,
  AgentStartPayload,
  QualityPayload,
  ToolCallPayload,
  TraceEvent,
} from './runs'

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function parseToolCall(e: TraceEvent): ToolCallPayload | null {
  const payload = asRecord(e.payload)
  if (!payload || typeof payload.tool !== 'string') return null
  return payload as ToolCallPayload
}

/** The agent's configuration off its `agent_start` event. */
export function parseAgentStart(e: TraceEvent): AgentStartPayload | null {
  if (e.type !== 'agent_start') return null
  return asRecord(e.payload) as AgentStartPayload | null
}

/** What an agent run spent, off its `agent_end` event. */
export function parseAgentEnd(e: TraceEvent): AgentEndPayload | null {
  if (e.type !== 'agent_end') return null
  return asRecord(e.payload) as AgentEndPayload | null
}

/** A `quality:<name>` check: a tool_call with a command and no `tool`. */
export function parseQualityCall(e: TraceEvent): QualityPayload | null {
  if (e.type !== 'tool_call') return null
  const payload = asRecord(e.payload)
  if (!payload || 'tool' in payload || typeof payload.command !== 'string') return null
  return payload as unknown as QualityPayload
}

/** False when the payload reports a failure (ok/passed false or a non-zero returncode). */
export function eventOk(e: TraceEvent): boolean {
  const payload = asRecord(e.payload)
  if (!payload) return true
  if (payload.ok === false || payload.passed === false) return false
  if (typeof payload.returncode === 'number' && payload.returncode !== 0) return false
  return true
}

/** Text color class of an event type in the events column. */
export const EVENT_TYPE_CLASS: Record<string, string> = {
  gate_fail: 't-red',
  error: 't-red',
  gate_pass: 't-green',
  tool_call: 't-cyan',
  handoff: 't-violet',
  agent_start: 't-purple',
  agent_end: 't-green',
}

// Args keys most likely to BE the call, in priority order.
const ARG_LABEL_KEYS = [
  'command',
  'cmd',
  'file_path',
  'path',
  'pattern',
  'query',
  'url',
  'prompt',
  'description',
]

const LABEL_MAX = 160

function oneLine(value: string): string {
  const flat = value.replaceAll(/\s+/g, ' ').trim()
  return flat.length > LABEL_MAX ? `${flat.slice(0, LABEL_MAX)}…` : flat
}

/** One-line summary of a tool's args: the call itself, not a JSON dump. */
export function argsSummary(args: Record<string, unknown> | undefined): string {
  if (!args) return ''
  for (const key of ARG_LABEL_KEYS) {
    const v = args[key]
    if (typeof v === 'string' && v.trim() !== '') return oneLine(v)
  }
  const parts: string[] = []
  for (const [key, v] of Object.entries(args)) {
    if (v == null) continue
    parts.push(`${key}=${typeof v === 'string' ? v : JSON.stringify(v)}`)
  }
  return oneLine(parts.join(' '))
}

// Leading indentation and list bullets of a console line ("  · quality test: …").
const LOG_BULLETS = /^[\s·•‣▸▹►└├─*-]+/

function logMessage(e: TraceEvent): string | null {
  if (e.type !== 'log') return null
  const message = asRecord(e.payload)?.message
  return typeof message === 'string' ? message : null
}

/** A `log` that only repeats the phase's `phase_start` ("▶ 05 test_1 code · quality …"). */
export function isPhaseHeaderLog(e: TraceEvent): boolean {
  const message = logMessage(e)
  return message != null && /^\s*▶\s*\d+\s/.test(message)
}

/** Row label for an event: "Read: src/x.py" for a tool call, the message for a log,
 *  else its name or type. */
export function eventLabel(e: TraceEvent): string {
  if (e.type === 'tool_call') {
    const call = parseToolCall(e)
    if (call?.tool) {
      const summary = argsSummary(call.args)
      if (e.name && e.name !== call.tool && e.name.startsWith(call.tool)) return oneLine(e.name)
      return summary ? `${call.tool}: ${summary}` : call.tool
    }
  }
  const message = logMessage(e)
  if (message != null) {
    const text = oneLine(message.replace(LOG_BULLETS, ''))
    if (text) return text
  }
  return e.name ?? e.type ?? ''
}

/** Lane colors for agents without a configured color, by lane index. */
export const AGENT_FALLBACK_COLORS = ['#c89bff', '#5ad2dd', '#94a3ff', '#e8b64a', '#f2a2c4']

function pickColor(c: string | null | undefined): string | null {
  return typeof c === 'string' && c.trim() ? c.trim() : null
}

/** The configured color, then the agent_start one, then the palette by lane index.
 *  An empty or whitespace color counts as unset. */
export function agentColor(
  configColor: string | null | undefined,
  payloadColor: string | null | undefined,
  index: number,
): string {
  return (
    pickColor(configColor) ??
    pickColor(payloadColor) ??
    AGENT_FALLBACK_COLORS[index % AGENT_FALLBACK_COLORS.length] ??
    '#c89bff'
  )
}

/** "#c89bff" + alpha → rgba() usable in inline styles. Invalid input → transparent. */
export function hexAlpha(hex: string, alpha: number): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m || !m[1]) return 'transparent'
  const n = Number.parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 0xff}, ${(n >> 8) & 0xff}, ${n & 0xff}, ${alpha})`
}
