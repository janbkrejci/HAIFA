import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunWaterfall from './RunWaterfall.vue'
import { AGENT_FALLBACK_COLORS } from '@/lib/events'
import type { PhaseRow, RunDetail } from '@/lib/runs'
import { MIN_BLOCK_PX } from '@/lib/waterfall'
import { detail, events, moreEvents } from '@/test/runsFixtures'

const NOW = Date.parse('2026-01-01T10:10:00Z')

function withAgent(): RunDetail {
  const d = detail()
  d.agents = [
    {
      agent: 'planner',
      coding_agent: 'claude',
      model: 'claude-opus-4',
      session_id: null,
      color: '',
      context_tokens: 50_000,
      context_window: 200_000,
      created_at: null,
      last_used_at: null,
    },
  ]
  return d
}

afterEach(() => {
  window.location.hash = ''
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

/** Dozens of short builds with retries, a running phase and queued ones, all of one owner. */
function longDetail(): RunDetail {
  const d = detail({ state: 'running', ended_at: null, duration_s: null })
  const base = d.phases.find((p) => p.kind === 'agent')!
  const start = Date.parse('2026-01-01T10:00:00Z')
  const iso = (sec: number) => new Date(start + sec * 1000).toISOString()
  const phases: PhaseRow[] = []
  for (let i = 0; i < 30; i++) {
    phases.push({ ...base, phase_id: `b${i}`, seq: i + 1, name: 'build', attempt: (i % 3) + 1, started_at: iso(i * 2), ended_at: iso(i * 2 + 2) })
  }
  phases.push({ ...base, phase_id: 'run', seq: 40, name: 'review', status: 'running', started_at: iso(60), ended_at: null })
  for (let i = 0; i < 3; i++) {
    phases.push({ ...base, phase_id: `q${i}`, seq: 50 + i, name: `next-${i}`, status: 'queued', started_at: null, ended_at: null })
  }
  d.phases = phases
  return d
}

function box(el: Element): { left: number; right: number } {
  const style = (el as HTMLElement).style
  const left = Number.parseFloat(style.left)
  return { left, right: left + Number.parseFloat(style.width) }
}

function overlapping(boxes: { left: number; right: number }[]): boolean {
  const sorted = [...boxes].sort((a, b) => a.left - b.left)
  return sorted.some((b, i) => i > 0 && b.left < sorted[i - 1]!.right - 1e-9)
}

describe('RunWaterfall', () => {
  it('shows the model as soon as a running agent lane arrives without a session or start event', async () => {
    const initial = detail({ state: 'running' })
    const running = { ...initial.phases.find((p) => p.kind === 'agent')!, status: 'running', ended_at: null, model: 'claude-opus-4' }
    initial.phases = []
    initial.agents = []
    const wrapper = mount(RunWaterfall, { props: { detail: initial, events: [], now: NOW } })
    expect(wrapper.find('[data-lane="agent:planner"]').exists()).toBe(false)

    await wrapper.setProps({ detail: { ...initial, phases: [running] } })

    const model = wrapper.find('[data-lane="agent:planner"] [data-test="lane-model"]')
    expect(model.text()).toContain('claude-opus-4')
    expect(model.find('img.model-icon').attributes('src')).toBe('/models/claude.png')
  })

  it('draws engineer, code and agent lanes with model, context and color', () => {
    const wrapper = mount(RunWaterfall, { props: { detail: withAgent(), events: events(), now: NOW } })
    expect(wrapper.findAll('[data-lane]').map((l) => l.attributes('data-lane'))).toEqual([
      'engineer',
      'code',
      'agent:planner',
    ])
    const planner = wrapper.find('[data-lane="agent:planner"]')
    const model = planner.find('[data-test="lane-model"]')
    expect(model.text()).toContain('claude-opus-4')
    expect(model.find('img.model-icon').attributes('src')).toBe('/models/claude.png')
    expect(planner.find('[data-test="lane-ctx"]').text()).toContain('25%')
    expect(planner.find('.lane-name').attributes('data-color')).toBe(AGENT_FALLBACK_COLORS[0])
    expect(wrapper.find('[title]').exists()).toBe(false)
  })

  it('draws blocks with name, description and failure', () => {
    const wrapper = mount(RunWaterfall, { props: { detail: detail(), events: events(), now: NOW } })
    const p1 = wrapper.find('button.block[data-phase="p1"]')
    expect(p1.text()).toContain('plan')
    expect(p1.find('.b-desc').text()).toBe('Naplánuj práci')
    expect(p1.find('.b-dur').text()).toBe('3m 00s')
    const p2 = wrapper.find('button.block[data-phase="p2"]')
    expect(p2.classes()).toContain('failed')
    expect(wrapper.find('[data-lane="code"] button.block[data-phase="p2"]').exists()).toBe(true)
  })

  it('draws a queued phase dashed in its lane', () => {
    const d = detail()
    d.phases.push({ ...d.phases[1]!, phase_id: 'p3', seq: 3, name: 'commit', status: 'queued', started_at: null, ended_at: null })
    const wrapper = mount(RunWaterfall, { props: { detail: d, events: [], now: NOW } })
    const queued = wrapper.find('button.block.queued[data-phase="p3"]')
    expect(queued.exists()).toBe(true)
    expect(queued.text()).toContain('ve frontě')
  })

  it('marks a failed tool call red', () => {
    const wrapper = mount(RunWaterfall, {
      props: { detail: detail(), events: [...events(), ...moreEvents()], now: NOW },
    })
    expect(wrapper.find('[data-phase="p2"] .tool-tick.err').exists()).toBe(true)
    const p1Ticks = wrapper.findAll('[data-phase="p1"] .tool-tick')
    expect(p1Ticks.length).toBeGreaterThan(0)
    expect(p1Ticks.some((t) => t.classes().includes('err'))).toBe(false)
  })

  it('selects a phase on click and deselects on a second click', async () => {
    const wrapper = mount(RunWaterfall, { props: { detail: detail(), events: [], now: NOW, phaseId: null } })
    await wrapper.find('button.block[data-phase="p1"]').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/runs/r-ok/p1')
    await wrapper.setProps({ phaseId: 'p1' })
    expect(wrapper.find('.block.selected').attributes('data-phase')).toBe('p1')
    await wrapper.find('button.block[data-phase="p1"]').trigger('click')
    expect(window.location.hash).toBe('#/r/haifa/runs/r-ok')
  })

  it('shows harness and model in the block tooltip', async () => {
    const wrapper = mount(RunWaterfall, {
      props: { detail: detail(), events: [], now: NOW },
      attachTo: document.body,
    })
    await wrapper.find('button.block[data-phase="p1"]').trigger('mouseenter')
    await flushPromises()
    const tip = document.body.querySelector('[data-test="tooltip"]')?.textContent ?? ''
    expect(tip).toContain('Harness: claude')
    expect(tip).toContain('Model: claude-opus')
    expect(tip).toContain('Naplánuj práci')
    await wrapper.find('button.block[data-phase="p1"]').trigger('mouseleave')
    await flushPromises()
    expect(document.body.querySelector('[data-test="tooltip"]')).toBeNull()
    expect(document.body.querySelector('[title]')).toBeNull()
    wrapper.unmount()
  })

  it('grows a running block with now', async () => {
    const d = detail({ state: 'running', ended_at: null, duration_s: null })
    const [code, agent] = d.phases
    d.phases = [
      { ...code!, status: 'success', ended_at: '2026-01-01T10:00:05+00:00' },
      { ...agent!, status: 'running', started_at: '2026-01-01T10:00:05+00:00', ended_at: null, duration_s: null },
    ]
    const start = Date.parse('2026-01-01T10:00:05Z')
    const wrapper = mount(RunWaterfall, { props: { detail: d, events: [], now: start + 10_000 } })
    const block = () => wrapper.find('button.block[data-phase="p1"]')
    const width = () => Number.parseFloat((block().element as HTMLElement).style.width)
    expect(block().find('.b-dur').text()).toBe('10.0s')
    expect(block().classes()).toContain('running')
    const before = width()
    await wrapper.setProps({ now: start + 30_000 })
    expect(block().find('.b-dur').text()).toBe('30.0s')
    expect(width()).toBeGreaterThan(before)
  })

  it('says so when the run has no phases', () => {
    const d = detail()
    d.phases = []
    const wrapper = mount(RunWaterfall, { props: { detail: d, events: [], now: NOW } })
    expect(wrapper.text()).toContain('Žádné fáze v trace.')
    expect(wrapper.find('[data-test="waterfall"]').exists()).toBe(false)
  })

  it('lays queued phases side by side instead of stacking them', () => {
    const d = detail()
    for (let i = 0; i < 3; i++) {
      d.phases.push({ ...d.phases.find((p) => p.kind === 'code')!, phase_id: `q${i}`, seq: 10 + i, name: `next-${i}`, status: 'queued', started_at: null, ended_at: null })
    }
    const wrapper = mount(RunWaterfall, { props: { detail: d, events: [], now: NOW } })
    const queued = wrapper.findAll('[data-lane="code"] button.block.queued')
    expect(queued.map((b) => b.attributes('data-phase'))).toEqual(['q0', 'q1', 'q2'])
    expect(queued.every((b) => !(b.element as HTMLElement).style.right)).toBe(true)
    const code = wrapper.findAll('[data-lane="code"] button.block').map((b) => box(b.element))
    expect(overlapping(code)).toBe(false)
  })

  it('scrolls a long run in one region holding the axis and every lane', () => {
    const wrapper = mount(RunWaterfall, { props: { detail: longDetail(), events: [], now: Date.parse('2026-01-01T10:05:00Z') } })
    const scroll = wrapper.find('[data-test="waterfall-scroll"]')
    expect(scroll.attributes('data-overflow')).toBe('true')
    expect(wrapper.findAll('[data-test="waterfall-scroll"]')).toHaveLength(1)
    expect(scroll.find('.axis-row').exists()).toBe(true)
    expect(scroll.findAll('[data-lane]')).toHaveLength(wrapper.findAll('[data-lane]').length)
    const canvas = scroll.find('[data-test="waterfall-canvas"]').element as HTMLElement
    const canvasPx = Number.parseFloat(canvas.style.width)
    expect(canvasPx).toBeGreaterThan(240 + 34 * MIN_BLOCK_PX)
    const blocks = wrapper.findAll('[data-lane="agent:planner"] button.block')
    expect(blocks).toHaveLength(34)
    const boxes = blocks.map((b) => box(b.element))
    expect(overlapping(boxes)).toBe(false)
    for (const b of boxes) expect(((b.right - b.left) / 100) * (canvasPx - 240)).toBeGreaterThanOrEqual(MIN_BLOCK_PX - 1e-6)
    expect(blocks.at(-1)!.classes()).toContain('queued')
  })

  it('keeps a short run at the region width', () => {
    const wrapper = mount(RunWaterfall, { props: { detail: detail(), events: [], now: NOW } })
    expect(wrapper.find('[data-test="waterfall-scroll"]').attributes('data-overflow')).toBeUndefined()
    expect((wrapper.find('[data-test="waterfall-canvas"]').element as HTMLElement).style.width).toBe('100%')
  })

  it('lays out for the measured width and follows a resize', async () => {
    let width = 240 + 1600
    let resize: (() => void) | undefined
    vi.spyOn(HTMLElement.prototype, 'clientWidth', 'get').mockImplementation(() => width)
    vi.stubGlobal(
      'ResizeObserver',
      class {
        constructor(cb: () => void) {
          resize = cb
        }
        observe() {}
        disconnect() {}
      },
    )
    const d = detail()
    const base = d.phases[1]!
    d.phases = Array.from({ length: 8 }, (_, i) => ({
      ...base,
      phase_id: `p${i}`,
      seq: i,
      started_at: new Date(Date.parse('2026-01-01T10:00:00Z') + i * 10_000).toISOString(),
      ended_at: new Date(Date.parse('2026-01-01T10:00:00Z') + i * 10_000 + 10_000).toISOString(),
    }))
    const wrapper = mount(RunWaterfall, { props: { detail: d, events: [], now: NOW } })
    await flushPromises()
    const scroll = () => wrapper.find('[data-test="waterfall-scroll"]')
    expect(scroll().attributes('data-overflow')).toBeUndefined()
    width = 240 + 600
    resize!()
    await flushPromises()
    expect(scroll().attributes('data-overflow')).toBe('true')
    expect(Number.parseFloat((wrapper.find('[data-test="waterfall-canvas"]').element as HTMLElement).style.width)).toBeGreaterThan(840)
  })
})
