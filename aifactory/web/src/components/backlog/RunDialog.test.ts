import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { chooseOption } from '@/test/select'
import RunDialog from './RunDialog.vue'
import type { RunCheck, RunStart, WriteError } from '@/lib/backlog'
import { runCheck, runStart, taskNode, taskRun } from '@/test/backlogFixtures'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

function dialog(
  check: RunCheck | null,
  extra: { error?: WriteError | null; result?: RunStart | null; loading?: boolean; body?: string } = {},
) {
  return mount(RunDialog, {
    props: {
      check,
      task: taskNode({ writes: ['src/'], effective: { workflow: 'plan-build', test: ['just', 'test'] } }),
      ...(extra.body !== undefined ? { body: extra.body } : {}),
      loading: extra.loading ?? false,
      busy: false,
      error: extra.error ?? null,
      result: extra.result ?? null,
    },
    attachTo: document.body,
  })
}

describe('RunDialog', () => {
  it('starts without warnings, with the note', async () => {
    const wrapper = dialog(runCheck())
    expect(wrapper.find('[data-test="config-warning"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="unmet-warning"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="run-force"]').exists()).toBe(false)
    await wrapper.find('[data-test="run-start"]').trigger('click')
    await wrapper.find('[data-test="run-note"]').setValue('  z UI ')
    await wrapper.find('[data-test="run-start"]').trigger('click')
    expect(wrapper.emitted('start')).toEqual([[{ force: false }], [{ note: 'z UI', force: false }]])
  })

  it('offers to commit the backlog only when the task is not in base', async () => {
    expect(dialog(runCheck()).find('[data-test="commit-backlog"]').exists()).toBe(false)
    const wrapper = dialog(runCheck({ in_base: false }))
    expect(wrapper.find('[data-test="not-in-base"]').text()).toContain('není commitnutý')
    // a task missing in base cannot start: the run would not find it
    expect(wrapper.find('[data-test="run-start"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="commit-backlog"]').trigger('click')
    expect(wrapper.emitted('commit')).toEqual([[]])
  })

  it('warns about uncommitted config (D4)', () => {
    const wrapper = dialog(
      runCheck({
        config: {
          base: 'main',
          commit: 'abcdef1234567890',
          clean: false,
          changes: [{ path: '.factory/workflows/x.yaml', status: 'untracked' }],
        },
      }),
    )
    const warning = wrapper.find('[data-test="config-warning"]')
    expect(warning.text()).toContain('main (abcdef1)')
    expect(warning.text()).toContain('untracked .factory/workflows/x.yaml')
    expect(warning.get('[data-test="config-commit-link"]').attributes('href')).toBe('#/r/haifa/factory/config_commit')
    expect(wrapper.find('[data-test="run-start"]').attributes('disabled')).toBeUndefined()
  })

  it('blocks a run with unmet dependencies and offers --force', async () => {
    const wrapper = dialog(
      runCheck({ unmet: [{ id: 'M01-S01-T01', reason: 'not_done', missing: ['M01-S01-T01'] }] }),
    )
    expect(wrapper.find('[data-unmet="M01-S01-T01"]').text()).toContain('not_done')
    expect(wrapper.find('[data-test="run-start"]').attributes('disabled')).toBeDefined()
    await wrapper.find('[data-test="run-note"]').setValue('přesto')
    await wrapper.find('[data-test="run-force"]').trigger('click')
    expect(wrapper.emitted('start')).toEqual([[{ note: 'přesto', force: true }]])
  })

  it('offers --force after an unmet_dependencies error', () => {
    const wrapper = dialog(runCheck(), {
      error: { message: 'depends on work not done', issues: [], code: 'unmet_dependencies' },
    })
    expect(wrapper.find('[data-test="write-error"]').text()).toContain('depends on work not done')
    expect(wrapper.find('[data-test="run-force"]').text()).toBe('Spustit přesto (ignorovat nesplněné závislosti)')
  })

  it('refuses while the task or another dashboard run is running', () => {
    const running = dialog(runCheck({ running: taskRun() }))
    expect(running.find('[data-test="run-running"] a').attributes('href')).toBe('#/r/haifa/runs/r-9')
    expect(running.find('[data-test="run-start"]').attributes('disabled')).toBeDefined()
    const busy = dialog(runCheck({ launcher_busy: true }))
    expect(busy.find('[data-test="launcher-busy-link"]').attributes('href')).toBe('#/r/haifa/runs')
    expect(busy.find('[data-test="run-start"]').attributes('disabled')).toBeDefined()
  })

  it('shows the started run, or that it is still starting', async () => {
    const started = dialog(runCheck(), { result: runStart() })
    expect(started.get('[data-test="run-open"]').attributes('href')).toBe('#/r/haifa/runs/r-9')
    expect(started.get('[data-test="run-open"]').text()).toBe('Otevřít běh')
    const pending = dialog(runCheck(), { result: runStart({ run: null, pending: true }) })
    expect(pending.find('[data-test="run-result"]').text()).toBe('Běh se spouští…')
    await pending.find('[data-test="run-cancel"]').trigger('click')
    expect(pending.emitted('cancel')).toHaveLength(1)
  })

  it('summarises the workflow, writes, base and task text', async () => {
    const wrapper = dialog(runCheck({ workflow: 'simple-sdlc', writes: ['aifactory/'] }), {
      body: 'Udělej **to**.',
    })
    expect(wrapper.get('[data-test="summary-workflow"]').text()).toBe('simple-sdlc')
    expect(wrapper.get('[data-test="summary-writes"]').text()).toBe('aifactory/')
    expect(wrapper.find('[data-test="summary-test"]').exists()).toBe(false)
    expect(wrapper.get('[data-test="summary-base"]').text()).toBe('main (abcdef1)')
    expect(wrapper.get('[data-test="summary-body"]').html()).toContain('<strong>to</strong>')
    // an older server without the effective values: the task's own
    const older = dialog(runCheck())
    expect(older.get('[data-test="summary-workflow"]').text()).toBe('plan-build')
    expect(older.get('[data-test="summary-writes"]').text()).toBe('src/')
  })

  it('sends the harness for this run and auto continue', async () => {
    const wrapper = dialog(runCheck())
    await chooseOption(wrapper, '[data-test="run-harness-name"]', 'codex')
    await wrapper.get('[data-test="run-model"]').setValue(' gpt-5 ')
    await chooseOption(wrapper, '[data-test="run-thinking"]', 'high')
    await wrapper.get('[data-test="run-auto"]').setValue(true)
    await wrapper.get('[data-test="run-start"]').trigger('click')
    expect(wrapper.emitted('start')).toEqual([
      [{ force: false, harness: 'codex', model: 'gpt-5', thinking: 'high', auto: true }],
    ])
  })

  it('shows the roster of the repo when the harness section opens', async () => {
    window.location.hash = '#/r/haifa/backlog/M01-S01-T02'
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ ok: true, data: { agents: [{ name: 'builder', harness: 'claude', model: 'opus' }, { name: 'reviewer' }], workflow_tasks: {} }, error: null, warnings: [] })),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = dialog(runCheck())
    const details = wrapper.get('[data-test="run-harness"]')
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/factory/roster')
    expect(wrapper.get('[data-agent="builder"]').text()).toContain('opus')
    expect(wrapper.get('[data-agent="reviewer"]').text()).toContain('výchozí')
  })
})
