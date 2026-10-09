import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PhaseDetail from './PhaseDetail.vue'
import { detail, events, moreEvents, okResponse, prompts } from '@/test/runsFixtures'
import type { PhaseRow } from '@/lib/runs'

let fetchMock: ReturnType<typeof vi.fn>

function stubPrompts(answer: () => Response | Promise<Response> = () => okResponse(prompts())) {
  fetchMock = vi.fn(async (_url: string) => answer())
  vi.stubGlobal('fetch', fetchMock)
}

beforeEach(() => stubPrompts())

afterEach(() => {
  vi.unstubAllGlobals()
})

function propsFor(phaseId: string, phaseOver: Partial<PhaseRow> = {}) {
  const d = detail()
  const phase = { ...d.phases.find((p) => p.phase_id === phaseId)!, ...phaseOver }
  return {
    runId: 'r-ok',
    phase,
    request: d.session?.request ?? null,
    gates: d.gates.filter((g) => g.phase_id === phaseId),
    envelopes: d.envelopes.filter((e) => e.phase_id === phaseId),
    events: [...events(), ...moreEvents()].filter((e) => e.phase_id === phaseId),
  }
}

function mountPhase(phaseId = 'p1', phaseOver: Partial<PhaseRow> = {}) {
  return mount(PhaseDetail, { props: propsFor(phaseId, phaseOver) })
}

function sections(wrapper: VueWrapper) {
  return wrapper.findAll('[data-section]').map((s) => s.attributes('data-section'))
}

async function open(wrapper: VueWrapper, id: string) {
  await wrapper.find(`[data-section="${id}"] [data-test="dsec-toggle"]`).trigger('click')
  await flushPromises()
  return wrapper.find(`[data-section="${id}"]`)
}

describe('PhaseDetail', () => {
  it('shows the header: name, status, tags, error, and closes', async () => {
    const wrapper = mountPhase('p1', { error: 'boom' })
    expect(wrapper.find('[data-test="phase-name"]').text()).toBe('plan')
    expect(wrapper.find('.d-head').text()).toContain('úspěch')
    expect(wrapper.find('[data-test="tag-agent"]').text()).toContain('planner')
    expect(wrapper.find('[data-test="tag-kind"]').text()).toContain('agent')
    expect(wrapper.find('[data-test="tag-attempt"]').text()).toContain('1/2')
    expect(wrapper.find('[data-stat="runtime"]').text()).toContain('3m 00s')
    expect(wrapper.find('[data-test="phase-error"]').text()).toBe('boom')
    await wrapper.find('[data-test="phase-close"]').trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('starts with every section collapsed and shows only the relevant ones', async () => {
    const plan = mountPhase('p1')
    await flushPromises()
    expect(sections(plan)).toEqual(['request', 'config', 'description', 'prompts', 'gates', 'cost', 'outputs'])
    expect(plan.findAll('.dsec-body')).toHaveLength(0)
    const code = mountPhase('p2')
    expect(sections(code)).toEqual(['request', 'gates', 'outputs'])
    expect(code.findAll('.dsec-body')).toHaveLength(0)
  })

  it('collapses everything on a phase change but not on a live update', async () => {
    const wrapper = mountPhase('p1')
    await open(wrapper, 'gates')
    await wrapper.find('[data-test="gate-toggle"]').trigger('click')
    await wrapper.find('[data-event="e1"] [data-test="event-toggle"]').trigger('click')
    expect(wrapper.findAll('.dsec-body')).toHaveLength(1)

    // A live update: a new phase object and new arrays for the same phase.
    const live = propsFor('p1')
    await wrapper.setProps({
      phase: { ...live.phase },
      events: [...live.events, { ...events()[1]!, rowid: 9, event_id: 'e9' }],
      gates: [...live.gates],
    })
    expect(wrapper.findAll('.dsec-body')).toHaveLength(1)
    expect(wrapper.find('[data-test="gate-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-event="e1"] [data-test="event-body"]').exists()).toBe(true)
    expect(wrapper.find('[data-event="e9"]').exists()).toBe(true)

    await wrapper.setProps(propsFor('p2'))
    expect(wrapper.findAll('.dsec-body')).toHaveLength(0)
    await wrapper.setProps(propsFor('p1'))
    expect(wrapper.findAll('.dsec-body')).toHaveLength(0)
    expect(wrapper.find('[data-test="event-body"]').exists()).toBe(false)
  })

  it('renders the request as markdown with a source tab', async () => {
    const section = await open(mountPhase('p1'), 'request')
    expect(section.find('[data-test="md-preview"] strong').text()).toBe('schéma')
    await section.find('[data-test="md-tab-source"]').trigger('click')
    expect(section.find('[data-test="md-source"]').text()).toContain('Navrhnout **schéma**.')
  })

  it('collapses a long request and expands it whole', async () => {
    const long = `# Zadání\n\n${Array.from({ length: 400 }, (_, i) => `slovo${i}`).join(' ')} keep what this says.`
    const wrapper = mount(PhaseDetail, { props: { ...propsFor('p1'), request: long } })
    const section = await open(wrapper, 'request')
    await section.find('[data-test="md-tab-source"]').trigger('click')
    const collapsed = section.find('[data-test="md-source"]').text()
    expect(collapsed.endsWith('…')).toBe(true)
    expect(collapsed.length).toBeLessThan(long.length)
    expect(collapsed).not.toContain('keep what this says.')
    const toggle = section.find('[data-test="request-toggle"]')
    expect(toggle.text()).toBe('Zobrazit celé zadání')
    await toggle.trigger('click')
    expect(section.find('[data-test="md-source"]').text()).toBe(long)
    expect(section.find('[data-test="request-toggle"]').text()).toBe('Sbalit zadání')
  })

  it('shows a short request whole, without a toggle', async () => {
    const section = await open(mountPhase('p1'), 'request')
    expect(section.find('[data-test="request-toggle"]').exists()).toBe(false)
  })

  it('shows the agent configuration', async () => {
    const section = await open(mountPhase('p1'), 'config')
    expect(section.find('[data-test="cfg-coding_agent"]').text()).toContain('claude')
    expect(section.find('[data-test="cfg-model"]').text()).toContain('claude-opus-4')
    expect(section.find('[data-test="cfg-model"] img').attributes('src')).toBe('/models/claude.png')
    expect(section.find('[data-test="cfg-thinking"]').text()).toContain('high')
    expect(section.findAll('[data-test="cfg-tools"] .cfg-chip').map((c) => c.text())).toEqual(['Read', 'Edit'])
    expect(section.find('[data-test="cfg-harness_engineering"]').text()).toContain('žádné')
    expect(section.find('[data-test="cfg-purpose"]').text()).toContain('plánuje')
    expect(section.find('[data-test="cfg-session"]').text()).toContain('sess-1')
  })

  it('falls back to the phase harness and model without agent_start', async () => {
    const wrapper = mount(PhaseDetail, {
      props: { ...propsFor('p1'), events: [] },
    })
    const section = await open(wrapper, 'config')
    expect(section.find('[data-test="cfg-coding_agent"]').text()).toContain('claude')
    expect(section.find('[data-test="cfg-model"]').text()).toContain('claude-opus')
    expect(section.find('[data-test="cfg-tools"]').exists()).toBe(false)
  })

  it('shows the description', async () => {
    const section = await open(mountPhase('p1'), 'description')
    expect(section.text()).toContain('Naplánuj práci')
  })

  it('loads the compiled prompts once and shows them collapsed', async () => {
    const wrapper = mountPhase('p1')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r-ok/phases/p1/prompts')
    const section = await open(wrapper, 'prompts')
    expect(section.find('.dsec-count').text()).toBe('(2)')
    const panels = section.findAll('[data-test="prompt-panel"]')
    expect(panels.map((p) => p.attributes('data-prompt'))).toEqual(['system', 'user'])
    expect(panels[0]!.find('[data-test="prompt-lines"]').text()).toBe('3 řádky')
    expect(panels[1]!.find('[data-test="prompt-lines"]').text()).toBe('1 řádek')
    expect(section.find('.prompt-body').exists()).toBe(false)
    expect(section.find('[data-test="prompts-legacy"]').exists()).toBe(false)
    await panels[0]!.find('[data-test="prompt-toggle"]').trigger('click')
    const body = wrapper.find('[data-prompt="system"] .prompt-body')
    expect(body.text()).toContain('You are the planner.')
    expect(body.find('strong').text()).toBe('well')
    await body.find('[data-test="md-tab-source"]').trigger('click')
    expect(wrapper.find('[data-prompt="system"] [data-test="md-source"]').text()).toContain('Plan **well**.')

    // A live update of the same phase neither refetches nor collapses.
    await wrapper.setProps({ phase: { ...propsFor('p1').phase } })
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(wrapper.find('[data-prompt="system"] .prompt-body').exists()).toBe(true)
  })

  it('says when the prompts are the agent’s last ones', async () => {
    stubPrompts(() => okResponse(prompts({ source: 'agent', legacy: true })))
    const section = await open(mountPhase('p1'), 'prompts')
    expect(section.find('[data-test="prompts-legacy"]').text()).toContain('poslední prompty agenta')
  })

  it('reports prompts that failed to load', async () => {
    stubPrompts(
      () =>
        new Response(
          JSON.stringify({ ok: false, data: null, error: { code: 'unknown_phase', message: 'x', path: null, id: null, issues: [] }, warnings: [] }),
          { status: 404 },
        ),
    )
    const section = await open(mountPhase('p1'), 'prompts')
    expect(section.find('[data-test="prompts-error"]').text()).toContain('nepodařilo')
  })

  it('ignores a prompts answer for a phase no longer shown', async () => {
    let resolve: (r: Response) => void = () => {}
    stubPrompts(() => new Promise<Response>((r) => (resolve = r)))
    const wrapper = mountPhase('p1')
    await wrapper.setProps(propsFor('p2'))
    resolve(okResponse(prompts()))
    await flushPromises()
    expect(wrapper.find('[data-section="prompts"]').exists()).toBe(false)
  })

  it('does not fetch prompts for a code phase', async () => {
    mountPhase('p2')
    await flushPromises()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows gates collapsed with their checks behind a toggle', async () => {
    const wrapper = mountPhase('p1')
    const section = await open(wrapper, 'gates')
    const gates = section.findAll('[data-test="gate"]')
    expect(gates).toHaveLength(2)
    expect(gates[0]!.classes()).toContain('pass')
    expect(gates[0]!.text()).toContain('prošel')
    expect(gates[0]!.find('[data-test="gate-checks-label"]').text()).toContain('1')
    expect(gates[1]!.classes()).toContain('fail')
    expect(gates[1]!.text()).toContain('neprošel')
    expect(gates[1]!.find('[data-test="gate-checks-label"]').text()).toContain('1 z 2 selhalo')
    expect(gates[1]!.find('[data-test="gate-attempt"]').text()).toContain('2')
    expect(section.find('[data-test="gate-body"]').exists()).toBe(false)

    await gates[1]!.find('[data-test="gate-toggle"]').trigger('click')
    const body = wrapper.find('[data-gate-id="2"] [data-test="gate-body"]')
    const checks = body.findAll('[data-test="gate-check"]')
    expect(checks).toHaveLength(2)
    expect(checks[0]!.find('pre.check-note-block').text()).toBe('exit 1\nFAILED test_x')
    expect(checks[1]!.find('.check-note').text()).toBe('clean')
    expect(body.find('[data-test="violations"]').text()).toContain('tests failed')
  })

  it('itemises the cost of an agent phase', async () => {
    const section = await open(mountPhase('p1'), 'cost')
    const rows = section.findAll('tbody tr')
    expect(rows.map((r) => r.attributes('data-row'))).toEqual([
      'vstup',
      'výstup',
      'thinking',
      'cache-cteni',
      'cache-zapis',
      'celkem',
    ])
    const cells = (key: string) =>
      section.findAll(`[data-row="${key}"] td`).map((td) => td.text().replace(/\s/g, ' '))
    expect(cells('vstup')).toEqual(['vstup', '100', '$0.1000'])
    expect(cells('thinking')).toEqual(['thinking', '10', '$0.0333'])
    expect(cells('cache-cteni')).toEqual(['cache čtení', '1 000', '$0.0300'])
    expect(cells('celkem')).toEqual(['celkem', '1 180', '$0.2500'])
    expect(section.find('[data-row="thinking"]').classes()).toContain('u-nested')
    expect(section.find('[data-row="celkem"]').classes()).toContain('u-total')
    expect(section.find('[data-test="cost-partial"]').exists()).toBe(false)
  })

  it('shows only the total cost without a breakdown', async () => {
    const wrapper = mount(PhaseDetail, {
      props: { ...propsFor('p1', { usage: null }), events: [] },
    })
    const section = await open(wrapper, 'cost')
    expect(section.findAll('tbody tr').map((r) => r.attributes('data-row'))).toEqual(['celkem'])
    expect(section.find('[data-row="celkem"]').text()).toContain('$0.2500')
    expect(section.find('[data-test="cost-partial"]').text()).toContain('jen součet')
  })

  it('takes the breakdown from agent_end when the phase has none', async () => {
    const section = await open(mountPhase('p1', { usage: null }), 'cost')
    expect(section.find('[data-row="vstup"]').text()).toContain('100')
    expect(section.find('[data-test="cost-partial"]').exists()).toBe(false)
  })

  it('shows outputs as highlighted envelopes', async () => {
    const section = await open(mountPhase('p1'), 'outputs')
    const envelope = section.find('[data-test="envelope"]')
    expect(envelope.find('.output-type').text()).toBe('PlanOutput')
    expect(envelope.text()).toContain('planner')
    expect(envelope.text()).toContain('pokus')
    expect(envelope.text()).toContain('platný')
    expect(envelope.find('pre .j-key').text()).toBe('"status"')
    expect(envelope.find('pre').text()).toContain('"summary": "a plan"')
  })

  it('shows events without opening anything and expands a tool call', async () => {
    const wrapper = mountPhase('p1')
    const col = wrapper.find('[data-test="events-col"]')
    expect(col.find('h3').text()).toContain('Události (3)')
    const tool = col.find('[data-type="tool_call"]')
    expect(tool.text()).toContain('Read: src/app/x.py')
    expect(tool.find('.e-type').classes()).toContain('t-cyan')
    expect(tool.find('[data-test="event-body"]').exists()).toBe(false)
    await tool.find('[data-test="event-toggle"]').trigger('click')
    const body = wrapper.find('[data-event="e2"] [data-test="event-body"]')
    expect(body.text()).toContain('argumenty')
    expect(body.find('.j-key').text()).toBe('"file_path"')
    expect(body.text()).toContain('výsledek')
    expect(body.text()).toContain("print('x')")
    const end = wrapper.find('[data-event="e4"]')
    expect(end.find('[data-stat="runtime"]').text()).toContain('3.0s')
    expect(end.find('[data-stat="tokens"]').text()).toContain('1.2k')
  })

  it('labels logs by their message and hides the phase header log', () => {
    const base = events()[0]!
    const log = (id: string, rowid: number, message: string) => ({
      ...base,
      event_id: id,
      rowid,
      phase_id: 'p1',
      type: 'log',
      name: 'build',
      payload: { message, level: 'info' },
    })
    const wrapper = mount(PhaseDetail, {
      props: {
        ...propsFor('p1'),
        events: [...propsFor('p1').events, log('h1', 50, '▶ 02 build  agent · builder'), log('l1', 51, '  · quality test: just check')],
      },
    })
    const col = wrapper.find('[data-test="events-col"]')
    expect(col.find('h3').text()).toContain('Události (4)')
    expect(col.find('[data-event="h1"]').exists()).toBe(false)
    expect(col.find('[data-event="l1"] .e-name').text()).toBe('quality test: just check')
    expect(col.find('[data-type="tool_call"] .e-name').text()).toBe('Read: src/app/x.py')
  })

  it('expands a quality check and a plain event', async () => {
    const wrapper = mountPhase('p2')
    const quality = wrapper.find('[data-event="e5"]')
    expect(quality.find('.e-name').classes()).toContain('t-red')
    await quality.find('[data-test="event-toggle"]').trigger('click')
    const meta = wrapper.find('[data-event="e5"] [data-test="quality-meta"]')
    expect(meta.find('code').text()).toBe('uv run pytest')
    expect(meta.find('[data-test="quality-returncode"]').text()).toBe('1')
    expect(meta.text()).toContain('neprošel')
    await wrapper.find('[data-event="e6"] [data-test="event-toggle"]').trigger('click')
    const body = wrapper.find('[data-event="e6"] [data-test="event-body"]')
    expect(body.text()).toContain('payload')
    expect(body.find('.j-str').text()).toBe('"fail"')
  })

  it('renders no native title anywhere', async () => {
    const wrapper = mountPhase('p1')
    for (const id of ['request', 'config', 'description', 'prompts', 'gates', 'cost', 'outputs']) await open(wrapper, id)
    for (const toggle of wrapper.findAll('[data-test="event-toggle"]')) await toggle.trigger('click')
    expect(wrapper.find('[title]').exists()).toBe(false)
  })
})
