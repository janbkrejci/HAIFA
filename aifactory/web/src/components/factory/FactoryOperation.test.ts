import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { ApiError, applyBasePull, fetchBasePullPlan, applyFactoryPlan, fetchFactoryPlan, fetchOverview, type FactoryPlan, type FactoryInitPlan, type FactoryUpdatePlan, type FactoryPullPlan } from '@/lib/api'
import { useLive, type LiveHandlers } from '@/lib/live'
import FactoryOperation from './FactoryOperation.vue'
import { answerDialog, openDialog } from '@/test/modal'
import { chooseOption } from '@/test/select'
import { deferred } from '@/test/deferred'
import { installPlan } from '@/test/factoryFixtures'
vi.mock('@/lib/api', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/api')>(), fetchFactoryPlan: vi.fn(), applyFactoryPlan: vi.fn(), fetchOverview: vi.fn(), fetchBasePullPlan: vi.fn(), applyBasePull: vi.fn() }))
vi.mock('@/lib/live', () => ({ useLive: vi.fn() }))
enableAutoUnmount(afterEach)
const binding = { harness: 'claude', model: 'sonnet', thinking: 'medium' }
function preview(extra: Partial<FactoryPullPlan> & { action: 'pull' }): FactoryPullPlan
function preview(extra: Partial<FactoryUpdatePlan> & { action: 'update' }): FactoryUpdatePlan
function preview(extra?: Partial<FactoryInitPlan>): FactoryInitPlan
function preview(extra: Partial<FactoryPlan> = {}): FactoryPlan {
  return { action: 'init', base: 'main', base_sha: 'a6f3e1c01234', remote: 'origin', digest: 'same-digest', blockers: [],
    files: [{ path: '.factory/manifest.yaml', action: 'create', diff: '', content: 'format: 1', binary: false }],
    provider: 'local', backlog_dir: 'backlog', specs_dir: 'specs', docs_dir: 'docs', agents: ['planner','builder'], workflows: ['simple-sdlc'],
    bindings: { planner: { ...binding }, builder: { ...binding } }, detected: { harnesses: { claude: { installed: true }, codex: { installed: false } } },
    available: { agents: ['planner','builder','reviewer','documenter','scout'].map(name => ({ name, purpose: name, default: name !== 'scout', ...binding })), workflows: [{ name: 'simple-sdlc', default: true }, { name: 'scout', default: false }] }, ...extra } as FactoryPlan
}
function operation(action: 'init' | 'update' | 'config_commit' | 'pull' = 'init') { return mount(FactoryOperation, { props: { repoId: 'a', action }, attachTo: document.body }) }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(fetchFactoryPlan).mockResolvedValue(preview())
  vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'a', state: 'ok', running: [] } as never], totals: {} })
  vi.mocked(applyFactoryPlan).mockResolvedValue({ commit: 'new-commit' })
})
afterEach(() => { document.body.innerHTML = '' })
describe('Factory operations', () => {
  it('replans thinking/null, every directory and agent/workflow selections, retaining overrides for added agents', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(installPlan())
    const w = operation(); await flushPromises()
    for (const name of ['planner', 'builder', 'reviewer', 'documenter']) {
      expect(w.get(`[data-test="model-${name}"]`).element).toHaveProperty('value', 'sonnet')
      expect(w.get(`[data-test="thinking-${name}"]`).element).toHaveProperty('value', 'medium')
    }
    for (const key of ['backlog_dir', 'specs_dir', 'docs_dir'] as const) {
      const count = vi.mocked(fetchFactoryPlan).mock.calls.length
      await w.get(`[data-test="install-${key}"]`).setValue(`custom-${key}`); await flushPromises()
      expect(fetchFactoryPlan).toHaveBeenCalledTimes(count + 1)
      expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options[key]).toBe(`custom-${key}`)
    }
    await w.get('[data-test="thinking-builder"]').setValue('high'); await flushPromises()
    await w.get('[data-test="model-builder"]').setValue(''); await flushPromises()
    await w.get('[data-test="thinking-reviewer"]').setValue(''); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.bind).toMatchObject({ builder: { thinking: 'high', model: null }, reviewer: { thinking: null }, planner: binding })
    const checkbox = (name: string) => w.findAll('label').find(label => label.text().startsWith(name) && label.find('input[type="checkbox"]').exists())!.get('input')
    await checkbox('documenter').setValue(false); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.agents).not.toContain('documenter')
    const scout = { harness: 'pi', model: null, thinking: null }
    vi.mocked(fetchFactoryPlan).mockResolvedValue(installPlan({ added_agents: ['scout'], bindings: { scout } }))
    await checkbox('scout').setValue(true); await flushPromises()
    // Select the workflow as well; the response includes the required scout binding.
    await w.findAll('label').filter(label => label.text() === 'scout').at(-1)!.get('input').setValue(true); await flushPromises()
    await w.get('[data-test="install-base"]').setValue('develop'); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options).toMatchObject({ workflows: ['simple-sdlc', 'scout'], agents: ['planner', 'builder', 'reviewer', 'scout'], bind: { builder: { model: null, thinking: 'high' } } })
  })
  it('adds workflow-required bindings without losing an existing override', async () => {
    const initial = preview()
    initial.available.agents = initial.available.agents.filter(agent => agent.name !== 'scout')
    vi.mocked(fetchFactoryPlan).mockResolvedValue(initial)
    const w = operation(); await flushPromises()
    await w.get('[data-test="model-builder"]').setValue('custom'); await flushPromises()
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ added_agents: ['scout'], bindings: { scout: { harness: 'pi', model: null, thinking: null } } }))
    await w.findAll('label').find(label => label.text() === 'scout')!.get('input').setValue(true); await flushPromises()
    expect(w.get('[data-test="model-scout"]').element).toHaveProperty('value', '')
    await w.get('[data-test="install-base"]').setValue('develop'); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.bind).toMatchObject({ scout: { harness: 'pi', model: null, thinking: null }, builder: { model: 'custom' } })
  })
  it('renders full content, text patches, binary and mode-only changes', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ files: [
      { path: '.factory/manifest.yaml', action: 'create', diff: '', content: 'format: 1\n' + 'full-content\n'.repeat(200), binary: false },
      { path: 'changed.txt', action: 'modify', diff: '@@ -1 +1 @@\n-old\n+new', content: null, binary: false },
      { path: 'asset.bin', action: 'modify', diff: '', content: null, binary: true },
      { path: 'script', action: 'modify', diff: '', content: null, binary: false, mode: '100755' },
    ] }))
    const w = operation(); await flushPromises()
    const files = w.findAll('[data-test="plan-file"]')
    expect(files).toHaveLength(4)
    expect(files[0]!.get('pre').text().match(/full-content/g)).toHaveLength(200)
    expect(files[1]!.get('[data-kind="del"]').text()).toBe('-old')
    expect(files[1]!.get('[data-kind="add"]').text()).toBe('+new')
    expect(files[2]!.get('[data-test="binary"]').text()).toBe('binární soubor')
    expect(files[3]!.text()).toContain('100755')
    expect(files[3]!.text()).toContain('změna režimu souboru')
  })
  it('applies once on double-click and offers the backlog after success', async () => {
    const applying = deferred<Awaited<ReturnType<typeof applyFactoryPlan>>>()
    vi.mocked(applyFactoryPlan).mockReturnValueOnce(applying.promise)
    const refreshed = vi.fn()
    window.addEventListener('factory-applied', refreshed)
    try {
      const w = operation(); await flushPromises()
      await w.get('[data-test="factory-perform"]').trigger('click')
      await w.get('[data-test="factory-perform"]').trigger('click')
      await answerDialog(true)
      await w.get('[data-test="factory-perform"]').trigger('click')
      expect(applyFactoryPlan).toHaveBeenCalledTimes(1)
      applying.resolve({ commit: 'confirmed-commit', warnings: ['result warning'] }); await flushPromises()
      expect(refreshed).toHaveBeenCalledTimes(1)
      expect(w.get('[data-test="factory-success"]').text()).toContain('result warning')
      expect(w.get('[data-test="factory-success"] a').attributes('href')).toBe('#/r/a/backlog')
    } finally { window.removeEventListener('factory-applied', refreshed) }
  })
  it('re-previews a changed pull digest and preserves preview/result warnings', async () => {
    vi.mocked(fetchBasePullPlan).mockResolvedValue(preview({ action: 'pull', before: 'old', after: 'next', envelopeWarnings: ['preview warning'] }))
    vi.mocked(applyBasePull).mockRejectedValueOnce(new ApiError('plan_changed', 'remote moved')).mockResolvedValueOnce({ after: 'latest', warnings: ['pull warning'] })
    const w = operation('pull'); await flushPromises()
    expect(w.text()).toContain('preview warning')
    vi.mocked(fetchBasePullPlan).mockResolvedValue(preview({ action: 'pull', before: 'old', after: 'latest', digest: 'latest-digest' }))
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(applyBasePull).toHaveBeenCalledTimes(1)
    expect(openDialog()).toBeNull()
    expect(w.text()).toContain('latest')
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(applyBasePull).toHaveBeenLastCalledWith('latest-digest', 'a')
    expect(w.text()).toContain('pull warning')
  })
  it.each(['init', 'pull'] as const)('blocks %s on incoming runs, rejects stale run responses and resumes after end', async action => {
    vi.mocked(fetchBasePullPlan).mockResolvedValue(preview({ action: 'pull', before: 'old', after: 'new' }))
    const w = operation(action); await flushPromises()
    const handlers = vi.mocked(useLive).mock.calls.at(-1)![0] as LiveHandlers
    const old = deferred<Awaited<ReturnType<typeof fetchOverview>>>()
    vi.mocked(fetchOverview).mockReturnValueOnce(old.promise)
    window.dispatchEvent(new Event('focus')); await flushPromises()
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'a', state: 'ok', running: [{ run_id: 'incoming', process: 'alive' }] }, { id: 'other', state: 'ok', running: [{ run_id: 'foreign', process: 'alive' }] }] as never, totals: {} })
    handlers.trace!({ seq: 1, events: 1, phases: 0, run_ids: ['incoming'], task_ids: [], runs_changed: true }); await flushPromises()
    old.resolve({ repos: [{ id: 'a', state: 'ok', running: [] }] as never, totals: {} }); await flushPromises()
    expect(w.text()).toContain('V repu běží 1 běh,')
    expect(w.text()).not.toContain('foreign')
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'a', state: 'ok', running: [{ run_id: 'incoming', process: 'ended' }] }] as never, totals: {} })
    handlers.resync!(); await flushPromises()
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeUndefined()
    expect(applyFactoryPlan).not.toHaveBeenCalled()
    expect(applyBasePull).not.toHaveBeenCalled()
  })
  it('drops pending plan/run responses and confirmation on repo unmount', async () => {
    const w = operation(); await flushPromises()
    await w.get('[data-test="factory-perform"]').trigger('click')
    w.unmount()
    expect(openDialog()).toBeNull()
    const late = deferred<FactoryPlan>()
    vi.mocked(fetchFactoryPlan).mockReturnValueOnce(late.promise)
    const old = operation(); await flushPromises(); old.unmount()
    const next = mount(FactoryOperation, { props: { repoId: 'b', action: 'init' }, attachTo: document.body }); await flushPromises()
    late.resolve(preview({ digest: 'old-repo', base: 'stale-repo' })); await flushPromises()
    expect(next.text()).not.toContain('stale-repo')
    expect(applyFactoryPlan).not.toHaveBeenCalled()
  })
  it('keeps bindings per agent, replans each edit and warns about absent CLI', async () => {
    const w = operation(); await flushPromises()
    expect(w.text()).toContain('format: 1')
    expect(w.text()).toContain('1 commit na main (a6f3e1c → nový), push na origin/main')
    await chooseOption(w, '[data-test="harness-builder"]', 'codex'); await flushPromises()
    const options = vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options
    expect(options.bind?.builder?.harness).toBe('codex')
    expect(options.bind?.planner?.harness).toBe('claude')
    expect(w.text()).toContain('CLI pro codex není nainstalované')
    await w.get('[data-test="model-builder"]').setValue('gpt-6.1-sol'); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.bind?.builder?.model).toBe('gpt-6.1-sol')
  })
  it('requires its own modal and cancellation never applies', async () => {
    const w = operation(); await flushPromises()
    await w.get('[data-test="factory-perform"]').trigger('click')
    expect(openDialog()?.textContent).toContain('Commitnout 1 souborů do main a pushnout na origin?')
    expect(applyFactoryPlan).not.toHaveBeenCalled()
    await answerDialog(false)
    expect(applyFactoryPlan).not.toHaveBeenCalled()
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(applyFactoryPlan).toHaveBeenCalledTimes(1)
    expect(vi.mocked(applyFactoryPlan).mock.calls[0]![0].digest).toBe('same-digest')
    expect(w.text()).toContain('new-commit')
    expect(w.emitted('success')).toHaveLength(1)
  })
  it('invalidates confirmation on changes and ignores late plans', async () => {
    const w = operation(); await flushPromises()
    await w.get('[data-test="factory-perform"]').trigger('click')
    const late = deferred<FactoryPlan>()
    vi.mocked(fetchFactoryPlan).mockReturnValueOnce(late.promise)
    await w.get('[data-test="install-base"]').setValue('develop')
    expect(openDialog()).toBeNull()
    await w.get('[data-test="install-base"]').setValue('main'); await flushPromises()
    late.resolve(preview({ base: 'stale', digest: 'stale' })); await flushPromises()
    expect(w.text()).not.toContain('1 commit na stale')
    expect(applyFactoryPlan).not.toHaveBeenCalled()
  })
  it('disables blockers and running processes but not machine warnings', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ warnings: [{ code: 'cli', message: 'machine warning' }] }))
    const w = operation(); await flushPromises()
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeUndefined()
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ blockers: [{ code: 'not_onboarded', message: 'requires manifest' }] }))
    await w.get('[data-test="install-base"]').setValue('develop'); await flushPromises()
    expect(w.text()).toContain('not_onboarded: requires manifest')
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    w.unmount()
    vi.mocked(fetchOverview).mockResolvedValue({ repos: [{ id: 'a', state: 'ok', running: [{ run_id: 'live', process: 'alive' }, { run_id: 'gone', process: 'ended' }] } as never], totals: {} })
    const busy = operation(); await flushPromises()
    expect(busy.text()).toContain('V repu běží 1 běh, počká se, až doběhne')
    expect(busy.get('a').attributes('href')).toBe('#/r/a/runs/live')
    expect(busy.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
  })
  it('shows rejected push and opens PR with the same digest and new confirmation', async () => {
    vi.mocked(applyFactoryPlan).mockRejectedValueOnce(new ApiError('push_failed', 'protected main'))
    const w = operation(); await flushPromises()
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(w.text()).toContain('protected main')
    expect(w.text()).toContain('V repozitáři se nic nezměnilo')
    await w.get('[data-test="factory-pr"]').trigger('click'); await flushPromises()
    expect(applyFactoryPlan).toHaveBeenCalledTimes(1)
    vi.mocked(applyFactoryPlan).mockResolvedValue({ pr: { url: 'http://localhost/pr/1' } })
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(vi.mocked(applyFactoryPlan).mock.calls[1]![0]).toMatchObject({ digest: 'same-digest', target: 'pr' })
    expect(w.text()).toContain('Běhy počkají na merge')
  })
  it('requires a second confirmation when the server changes the plan', async () => {
    const w = operation(); await flushPromises()
    vi.mocked(applyFactoryPlan).mockRejectedValueOnce(new ApiError('plan_changed', 'stale'))
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ digest: 'new' }))
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(w.text()).toContain('Plán se změnil')
    expect(openDialog()).toBeNull()
    expect(applyFactoryPlan).toHaveBeenCalledTimes(1)
    await w.get('[data-test="factory-perform"]').trigger('click'); await answerDialog(true)
    expect(vi.mocked(applyFactoryPlan).mock.calls[1]![0].digest).toBe('new')
  })
  it('previews pull and sends only its reviewed digest after confirmation', async () => {
    vi.mocked(fetchBasePullPlan).mockResolvedValue(preview({ action: 'pull', before: 'old', after: 'new' }))
    vi.mocked(applyBasePull).mockResolvedValue({ after: 'new' })
    const w = operation('pull'); await flushPromises()
    expect(applyBasePull).not.toHaveBeenCalled()
    await w.get('[data-test="factory-perform"]').trigger('click')
    expect(openDialog()?.textContent).toContain('Stáhnout konfiguraci z origin/main?')
    await answerDialog(true)
    expect(applyBasePull).toHaveBeenCalledWith('same-digest','a')
    expect(applyFactoryPlan).not.toHaveBeenCalled()
  })
  it('can edit Azure choices and discards the old modal', async () => {
    const w = operation(); await flushPromises()
    await chooseOption(w, '[data-test="install-provider"]', 'azure')
    await flushPromises()
    const organization = w.findAll('label').find(label => label.text().startsWith('Azure organizace'))!
    await organization.get('input').setValue('my-org'); await flushPromises()
    expect(w.text()).toContain('Azure organizace')
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.provider).toBe('azure')
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.azure?.organization).toBe('my-org')
  })
  it('offers a retry when the run state cannot be verified', async () => {
    vi.mocked(fetchOverview).mockRejectedValueOnce(new Error('offline'))
    const w = operation(); await flushPromises()
    expect(w.get('[data-test="factory-runs-failed"]').text()).toContain('nepodařilo ověřit')
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeDefined()
    await w.get('[data-test="factory-runs-retry"]').trigger('click'); await flushPromises()
    expect(w.find('[data-test="factory-runs-failed"]').exists()).toBe(false)
    expect(w.get('[data-test="factory-perform"]').attributes('disabled')).toBeUndefined()
  })
  it('says per action that an empty plan has nothing to do', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ action: 'config_commit', files: [] } as never))
    const w = operation('config_commit'); await flushPromises()
    expect(w.get('[data-test="factory-plan-empty"]').text()).toBe('Konfigurace je commitnutá, není co commitnout.')
  })
  it('prefills the detected test command and sends an edited one', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ test_command: { command: 'bun test', source: 'detected', candidates: [], written: true } }))
    const w = operation(); await flushPromises()
    const field = w.get('[data-test="install-test_command"]')
    expect((field.element as HTMLInputElement).value).toBe('bun test')
    await field.setValue('just check'); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.test_command).toBe('just check')
  })
  it('replans takeover and migration choices', async () => {
    vi.mocked(fetchFactoryPlan).mockResolvedValue(preview({ action: 'update', update: {
      items: [{ type: 'agent', name: 'builder', action: 'conflict', merge_available: true, files: [{ file: 'system.md', status: 'conflict', diff: null, ours_diff: '+ours', theirs_diff: '+theirs' }] }],
      migrations: [{ id: 'm1', title: 'Migration one', diff: '+migrate', selected: false, applied: false }],
    } }))
    const w = operation('update'); await flushPromises()
    expect(w.text()).toContain('Změněno v obou')
    expect(w.text()).toContain('+ours'); expect(w.text()).toContain('+theirs')
    await w.findAll('input[type="checkbox"]')[0]!.setValue(true); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.take).toEqual(['agent/builder:system.md'])
    await w.findAll('input[type="checkbox"]')[2]!.setValue(true); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options.migrate).toEqual(['m1'])
    await w.findAll('input[type="checkbox"]')[1]!.setValue(true); await flushPromises()
    expect(vi.mocked(fetchFactoryPlan).mock.calls.at(-1)![0].options).toMatchObject({ take: [], merge: ['agent/builder'] })
  })
})
