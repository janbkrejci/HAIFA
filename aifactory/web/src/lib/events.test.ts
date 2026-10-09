import { describe, expect, it } from 'vitest'
import {
  AGENT_FALLBACK_COLORS,
  agentColor,
  hexAlpha,
  argsSummary,
  eventLabel,
  eventOk,
  isPhaseHeaderLog,
  parseAgentEnd,
  parseAgentStart,
  parseQualityCall,
  parseToolCall,
} from './events'
import type { TraceEvent } from './runs'

function event(over: Partial<TraceEvent>): TraceEvent {
  return {
    rowid: 1,
    event_id: 'e1',
    adw_id: 'r1',
    phase_id: 'p1',
    parent_id: null,
    type: 'log',
    name: 'note',
    payload: null,
    tokens: null,
    started_at: null,
    ended_at: null,
    ...over,
  }
}

describe('events', () => {
  it('summarises tool args by the most telling key', () => {
    expect(argsSummary({ command: 'bun  test\nsrc' })).toBe('bun test src')
    expect(argsSummary({ file_path: 'a.py', limit: 3 })).toBe('a.py')
    expect(argsSummary({ a: 1, b: 'x' })).toBe('a=1 b=x')
    expect(argsSummary(undefined)).toBe('')
  })

  it('labels tool calls and other events', () => {
    const tool = event({ type: 'tool_call', name: 'Read', payload: { tool: 'Read', args: { file_path: 'a.py' } } })
    expect(parseToolCall(tool)?.tool).toBe('Read')
    expect(eventLabel(tool)).toBe('Read: a.py')
    const named = event({ type: 'tool_call', name: 'bash: ls -la', payload: { tool: 'bash', args: { command: 'ls' } } })
    expect(eventLabel(named)).toBe('bash: ls -la')
    expect(eventLabel(event({ name: null, type: 'error' }))).toBe('error')
    expect(parseToolCall(event({ payload: [1] }))).toBeNull()
  })

  it('labels a log by its message on one line, without indent or bullet', () => {
    const log = (message: unknown) => event({ type: 'log', name: 'test_1', payload: { message, level: 'info' } })
    expect(eventLabel(log('  · quality test: just check'))).toBe('quality test: just check')
    expect(eventLabel(log('  └ planner used 1,200 tokens\n · $0.0100'))).toBe('planner used 1,200 tokens · $0.0100')
    expect(eventLabel(log('  ✓ test_1 3.0s'))).toBe('✓ test_1 3.0s')
    expect(eventLabel(log(''))).toBe('test_1')
    expect(eventLabel(log(42))).toBe('test_1')
    expect(eventLabel(event({ type: 'log', name: 'note', payload: null }))).toBe('note')
    // Other types keep their name even with a message in the payload.
    expect(eventLabel(event({ type: 'gate_pass', name: 'g', payload: { message: 'x' } }))).toBe('g')
  })

  it('tells the log that repeats the phase header', () => {
    const log = (message: string) => event({ type: 'log', name: 'test_1', payload: { message } })
    expect(isPhaseHeaderLog(log('▶ 05 test_1  code · quality  run checks'))).toBe(true)
    expect(isPhaseHeaderLog(log('  · quality test: just check'))).toBe(false)
    expect(isPhaseHeaderLog(event({ type: 'phase_start', payload: { message: '▶ 05 x' } }))).toBe(false)
    expect(isPhaseHeaderLog(event({ type: 'log', payload: null }))).toBe(false)
  })

  it('parses quality checks', () => {
    const quality = event({
      type: 'tool_call',
      name: 'quality:test',
      payload: { area: 'test', command: 'uv run pytest', returncode: 1, passed: false },
    })
    expect(parseQualityCall(quality)?.command).toBe('uv run pytest')
    expect(parseQualityCall(quality)?.returncode).toBe(1)
    expect(parseToolCall(quality)).toBeNull()
    const tool = event({ type: 'tool_call', payload: { tool: 'Bash', command: 'ls' } })
    expect(parseQualityCall(tool)).toBeNull()
    expect(parseQualityCall(event({ type: 'log', payload: { command: 'x' } }))).toBeNull()
  })

  it('tells failed events', () => {
    expect(eventOk(event({ type: 'tool_call', payload: { tool: 'Read', ok: false } }))).toBe(false)
    expect(eventOk(event({ type: 'tool_call', payload: { command: 'x', passed: false } }))).toBe(false)
    expect(eventOk(event({ type: 'tool_call', payload: { command: 'x', returncode: 2 } }))).toBe(false)
    expect(eventOk(event({ type: 'tool_call', payload: { tool: 'Read', ok: true } }))).toBe(true)
    expect(eventOk(event({ payload: null }))).toBe(true)
  })

  it('parses agent start and end payloads', () => {
    expect(parseAgentStart(event({ type: 'agent_start', payload: { model: 'm' } }))?.model).toBe('m')
    expect(parseAgentStart(event({ type: 'log', payload: { model: 'm' } }))).toBeNull()
    expect(parseAgentEnd(event({ type: 'agent_end', payload: { cost: 0.5 } }))?.cost).toBe(0.5)
    expect(parseAgentEnd(event({ type: 'agent_end', payload: 'x' }))).toBeNull()
  })
})

describe('agent colors', () => {
  it('treats an empty color as unset and falls back to the palette', () => {
    expect(agentColor('', null, 1)).toBe(AGENT_FALLBACK_COLORS[1])
    expect(agentColor('  ', '', 6)).toBe(AGENT_FALLBACK_COLORS[1])
    expect(agentColor(undefined, undefined, 0)).toBe(AGENT_FALLBACK_COLORS[0])
  })

  it('prefers the configured color, then the agent_start one', () => {
    expect(agentColor('#123456', '#abcdef', 0)).toBe('#123456')
    expect(agentColor(null, '#abcdef', 0)).toBe('#abcdef')
  })

  it('turns hex into rgba', () => {
    expect(hexAlpha('#ff0000', 0.5)).toBe('rgba(255, 0, 0, 0.5)')
    expect(hexAlpha('red', 1)).toBe('transparent')
  })
})
