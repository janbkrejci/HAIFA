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

const ROSTER: FactoryRoster = {
  agents: [
    { name: 'builder', purpose: 'Build code', harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium' },
    { name: 'reviewer', purpose: 'Review' },
  ],
  workflow_tasks: {},
  presets: {
    claude: { harness: 'claude', model: 'claude-opus-5-5', thinking: 'medium' },
    codex: { harness: 'codex', model: 'gpt-6.1-sol', thinking: 'medium' },
  },
  thinking_levels: ['off', 'low', 'medium', 'high'],
  workflow_overrides: [{ workflow: 'simple-sdlc', step: 'review', agent: 'reviewer', harness: 'codex', model: null, thinking: 'high' }],
}

const bind = (name: string, harness: string, model: string) => ({ name, harness, model, thinking: 'medium' })
const PREVIEW: RosterChangeResult = {
  before: [bind('builder', 'claude', 'claude-opus-5-5'), bind('reviewer', 'claude', 'claude-opus-5-5')],
  agents: [bind('builder', 'codex', 'gpt-6.1-sol'), bind('reviewer', 'codex', 'gpt-6.1-sol')],
  diff: '--- agents.yaml\n+++ agents.yaml\n@@ -1 +1 @@\n-  harness: claude\n+  harness: codex',
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
  it('lists the agents, the detected harnesses, the thinking levels and the step overrides', async () => {
    const w = setup()
    await flushPromises()
    expect(w.findAll('[data-test^="roster-agent-"]').map((r) => r.attributes('data-test'))).toEqual(['roster-agent-builder', 'roster-agent-reviewer'])
    expect(await selectLabels(w, '[data-test="roster-agent-builder"] [data-test="roster-harness"]')).toEqual(['Podle výchozích', 'claude', 'codex'])
    expect(await selectLabels(w, '[data-test="roster-agent-builder"] [data-test="roster-thinking"]')).toEqual(['Podle výchozích', 'off', 'low', 'medium', 'high'])
    const models = [...w.element.querySelectorAll('datalist option')].map((o) => (o as HTMLOptionElement).value)
    expect(models).toEqual(['claude-opus-5-5', 'gpt-6.1-sol'])
    expect(w.get('[data-test="roster-overrides"]').text()).toContain('simple-sdlc')
    expect(w.get('[data-test="roster-overrides"]').text()).toContain('codex')
  })

  it('previews a preset, saves it and points to the config commit', async () => {
    const w = setup()
    await flushPromises()
    await w.get('[data-test="roster-preset-codex"]').trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ preset: 'codex', dry_run: true }, 'a')
    const pending = w.get('[data-test="roster-pending"]')
    expect(pending.text()).toContain('builder: claude · claude-opus-5-5 · medium → codex · gpt-6.1-sol · medium')
    expect(pending.find('[data-kind="add"]').text()).toContain('harness: codex')
    await w.get('[data-test="roster-save"]').trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ preset: 'codex', dry_run: false }, 'a')
    expect(w.emitted('saved')).toHaveLength(1)
    expect(api.roster).toHaveBeenCalledTimes(2)
    expect(w.get('[data-test="roster-saved"]').text()).toContain('Běhy použijí změnu až po commitu konfigurace')
    await w.get('[data-test="roster-commit"]').trigger('click')
    expect(w.emitted('commit')).toHaveLength(1)
  })

  it('previews only the changed fields of one agent', async () => {
    const w = setup()
    await flushPromises()
    const row = '[data-test="roster-agent-builder"]'
    expect(w.find(`${row} [data-test="roster-preview"]`).exists()).toBe(false)
    await chooseOption(w, `${row} [data-test="roster-harness"]`, 'codex')
    await w.get(`${row} [data-test="roster-model"]`).setValue('gpt-6.1-sol')
    await w.get(`${row} [data-test="roster-preview"]`).trigger('click')
    await flushPromises()
    expect(api.save).toHaveBeenLastCalledWith({ agent: 'builder', harness: 'codex', model: 'gpt-6.1-sol', dry_run: true }, 'a')
    expect(w.emitted('busy')?.at(-1)).toEqual([true])
    await w.get('[data-test="roster-discard"]').trigger('click')
    expect(w.find('[data-test="roster-pending"]').exists()).toBe(false)
    expect((w.get(`${row} [data-test="roster-model"]`).element as HTMLInputElement).value).toBe('claude-opus-5-5')
  })

  it('refuses to preview a cleared value and shows a rejected change', async () => {
    const w = setup()
    await flushPromises()
    const row = '[data-test="roster-agent-builder"]'
    await w.get(`${row} [data-test="roster-model"]`).setValue('')
    expect(w.get(`${row} [data-test="roster-preview"]`).attributes('disabled')).toBeDefined()
    await w.get(`${row} [data-test="roster-model"]`).setValue('nonsense')
    api.save.mockRejectedValueOnce(new ApiError('invalid_config', 'unknown model nonsense'))
    await w.get(`${row} [data-test="roster-preview"]`).trigger('click')
    await flushPromises()
    expect(w.get('[data-test="roster-error"]').text()).toBe('unknown model nonsense')
    expect(w.find('[data-test="roster-pending"]').exists()).toBe(false)
  })
})
