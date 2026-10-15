import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { ApiError, type FactoryRoster, type RosterChangeResult } from '@/lib/api'
import { chooseOption, selectLabels } from '@/test/select'
import RosterEditor from './RosterEditor.vue'

const api = vi.hoisted(() => ({ roster: vi.fn(), save: vi.fn(), check: vi.fn() }))
vi.mock('@/lib/api', async (original) => ({
  ...(await original<object>()),
  fetchFactoryRoster: api.roster,
  saveFactoryRoster: api.save,
  fetchMachineCheck: api.check,
}))

const LIB = { harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium' }
const ROSTER: FactoryRoster = {
  agents: [
    { name: 'builder', purpose: 'Build code', harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium', origin: 'repo', overridden: ['harness'], inherited: null },
    { name: 'reviewer', purpose: 'Review', harness: 'claude', model: 'claude-sonnet-5', thinking: 'high', origin: 'library',
      overridden: ['model', 'thinking'], inherited: LIB },
    { name: 'planner', harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium', origin: 'library', overridden: [], inherited: LIB },
  ],
  workflow_tasks: {},
  presets: {
    claude: { harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium' },
    codex: { harness: 'codex', model: 'gpt-6.1-sol', thinking: 'medium' },
  },
  thinking_levels: ['off', 'low', 'medium', 'high'],
  workflow_overrides: [{ workflow: 'simple-sdlc', step: 'review', agent: 'reviewer', harness: 'codex', model: null, thinking: 'high' }],
}

const bind = (name: string, harness: string, model: string, thinking = 'medium') => ({ name, harness, model, thinking })
const PREVIEW: RosterChangeResult = {
  before: [bind('builder', 'claude', 'claude-opus-5-5')],
  agents: [bind('builder', 'claude', 'gpt-x')],
  diff: '--- agents.yaml\n+++ agents.yaml\n@@ -1 +1 @@\n-  model: claude-opus-5-5\n+  model: gpt-x',
  changed: true,
}
const RESET: RosterChangeResult = {
  before: [bind('reviewer', 'claude', 'claude-sonnet-5', 'high')],
  agents: [bind('reviewer', 'claude', 'claude-opus-5-5')],
  diff: '--- agents.yaml\n+++ agents.yaml\n@@ -1,3 +1 @@\n   - name: reviewer\n-    model: claude-sonnet-5\n-    thinking: high',
  changed: true,
}

function setup() {
  api.roster.mockResolvedValue(ROSTER)
  api.check.mockResolvedValue({
    ok: true, checked_at: 'now', cached: false, harness_repos: { claude: 1, codex: 0, pi: 0 },
    findings: [{ code: 'harness_missing', scope: 'machine', severity: 'info', message: 'harness pi (pi) is not installed', fix: null, action: null }],
  })
  api.save.mockResolvedValue(PREVIEW)
  return mount(RosterEditor, { props: { repoId: 'a' }, attachTo: document.body })
}

enableAutoUnmount(afterEach)
afterEach(() => {
  vi.clearAllMocks()
  document.body.innerHTML = ''
})

describe('RosterEditor', () => {
  it('lists each agent once with harness, model and thinking, inherited or overridden, and the step overrides', async () => {
    const w = setup()
    await flushPromises()
    expect(w.findAll('[data-test^="roster-agent-"]').map((r) => r.attributes('data-test')))
      .toEqual(['roster-agent-builder', 'roster-agent-reviewer', 'roster-agent-planner'])
    const reviewer = w.get('[data-test="roster-agent-reviewer"]')
    expect(reviewer.text()).toContain('claude-sonnet-5')
    expect(reviewer.text()).toContain('high')
    expect(reviewer.get('[data-test="roster-inherited-harness"]').text()).toBe('zděděno')
    expect(reviewer.get('[data-test="roster-overridden-model"]').text()).toBe('přepsáno')
    await reviewer.get('[data-test="roster-overridden-model"]').trigger('focusin')
    expect(document.body.querySelector('[data-test="tooltip"]')?.textContent).toContain('Zděděno: claude-opus-5-5')
    await reviewer.get('[data-test="roster-overridden-model"]').trigger('focusout')
    expect(reviewer.find('[data-test="roster-overridden-thinking"]').exists()).toBe(true)
    expect(reviewer.get('[data-test="roster-origin"]').text()).toBe('z knihovny')
    // the repo's own copy has no inherited values: no labels, no reset, but the move
    const builder = w.get('[data-test="roster-agent-builder"]')
    expect(builder.find('[data-test^="roster-overridden-"]').exists()).toBe(false)
    expect(builder.find('[data-test^="roster-inherited-"]').exists()).toBe(false)
    expect(builder.find('[data-test="roster-reset"]').exists()).toBe(false)
    expect(builder.find('[data-test="item-move-agent-builder"]').exists()).toBe(true)
    expect(builder.get('[data-test="roster-own"]').text()).toBe('vlastní kopie')
    // nothing overridden: nothing to reset
    expect(w.find('[data-test="roster-agent-planner"] [data-test="roster-reset"]').exists()).toBe(false)
    expect(reviewer.find('[data-test="roster-reset"]').exists()).toBe(true)
    expect(reviewer.find('[data-test="item-move-agent-reviewer"]').exists()).toBe(false)
    expect(w.find('[data-test^="roster-preset-"]').exists()).toBe(false)
    expect(w.find('h2').exists()).toBe(false)
    expect(w.get('[data-test="roster-overrides"]').text()).toContain('simple-sdlc')
    expect(w.get('[data-test="roster-overrides"]').text()).toContain('codex')
  })

  it('edits one agent: offers the detected harnesses and thinking levels, previews the changed fields and saves', async () => {
    const w = setup()
    await flushPromises()
    const row = '[data-test="roster-agent-builder"]'
    expect(w.find(`${row} [data-test="roster-model"]`).exists()).toBe(false)
    await w.get(`${row} [data-test="roster-edit"]`).trigger('click')
    expect(await selectLabels(w, `${row} [data-test="roster-harness"]`)).toEqual(['claude', 'codex'])
    expect(await selectLabels(w, `${row} [data-test="roster-thinking"]`)).toEqual(['off', 'low', 'medium', 'high'])
    const models = [...w.element.querySelectorAll('datalist option')].map((o) => (o as HTMLOptionElement).value)
    expect(models).toEqual(['claude-opus-5-5', 'gpt-6.1-sol', 'claude-sonnet-5'])
    expect(w.get(`${row} [data-test="roster-preview"]`).attributes('disabled')).toBeDefined()
    await chooseOption(w, `${row} [data-test="roster-harness"]`, 'codex')
    await w.get(`${row} [data-test="roster-model"]`).setValue('gpt-x')
    await w.get(`${row} [data-test="roster-preview"]`).trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ agent: 'builder', harness: 'codex', model: 'gpt-x', dry_run: true }, 'a')
    expect(w.emitted('busy')?.at(-1)).toEqual([true])
    // the preview is right under its agent
    const pending = w.get('[data-test="roster-pending"]')
    expect(pending.element.closest('tr')?.previousElementSibling?.getAttribute('data-test')).toBe('roster-agent-builder')
    expect(pending.text()).toContain('builder: claude · claude-opus-5-5 · medium → claude · gpt-x · medium')
    await w.get('[data-test="roster-save"]').trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ agent: 'builder', harness: 'codex', model: 'gpt-x', dry_run: false }, 'a')
    expect(w.emitted('saved')).toHaveLength(1)
    expect(api.roster).toHaveBeenCalledTimes(2)
    expect(w.find(`${row} [data-test="roster-model"]`).exists()).toBe(false)
    expect(w.get('[data-test="roster-saved"]').text()).toContain('Běhy použijí změnu až po commitu konfigurace')
    expect(w.find('[data-test="roster-commit"]').exists()).toBe(false)
    expect(w.text()).not.toContain('Commitnout konfiguraci')
  })

  it('returns the overrides of a library agent to the inherited values', async () => {
    const w = setup()
    await flushPromises()
    api.save.mockResolvedValue(RESET)
    await w.get('[data-test="roster-agent-reviewer"] [data-test="roster-reset"]').trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ agent: 'reviewer', reset: ['model', 'thinking'], dry_run: true }, 'a')
    expect(w.get('[data-test="roster-pending"]').text()).toContain('návrat na zděděné hodnoty')
    expect(w.get('[data-test="roster-pending"]').text()).toContain('reviewer: claude · claude-sonnet-5 · high → claude · claude-opus-5-5 · medium')
    await w.get('[data-test="roster-save"]').trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ agent: 'reviewer', reset: ['model', 'thinking'], dry_run: false }, 'a')
    expect(api.roster).toHaveBeenCalledTimes(2)
  })

  it('emits the move of an own copy', async () => {
    const w = setup()
    await flushPromises()
    await w.get('[data-test="item-move-agent-builder"]').trigger('click')
    expect(w.emitted('move')).toEqual([['builder']])
  })

  it('refuses to preview a cleared value and shows a rejected change', async () => {
    const w = setup()
    await flushPromises()
    const row = '[data-test="roster-agent-builder"]'
    await w.get(`${row} [data-test="roster-edit"]`).trigger('click')
    await w.get(`${row} [data-test="roster-model"]`).setValue('')
    expect(w.get(`${row} [data-test="roster-preview"]`).attributes('disabled')).toBeDefined()
    expect(w.get(row).text()).toContain('Hodnotu nejde smazat')
    await w.get(`${row} [data-test="roster-model"]`).setValue('nonsense')
    api.save.mockRejectedValueOnce(new ApiError('invalid_config', 'unknown model nonsense'))
    await w.get(`${row} [data-test="roster-preview"]`).trigger('click')
    await flushPromises()
    expect(w.get('[data-test="roster-error"]').text()).toBe('unknown model nonsense')
    expect(w.find('[data-test="roster-pending"]').exists()).toBe(false)
    await w.get(`${row} [data-test="roster-cancel"]`).trigger('click')
    expect(w.find(`${row} [data-test="roster-model"]`).exists()).toBe(false)
  })
})
