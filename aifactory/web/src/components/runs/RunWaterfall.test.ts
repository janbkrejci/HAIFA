import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import RunWaterfall from './RunWaterfall.vue'
import { AGENT_FALLBACK_COLORS } from '@/lib/events'
import type { RunDetail } from '@/lib/runs'
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
})

describe('RunWaterfall', () => {
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
})
