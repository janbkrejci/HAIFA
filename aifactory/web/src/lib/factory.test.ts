import { afterEach, describe, expect, it, vi } from 'vitest'
import { installPlan } from '@/test/factoryFixtures'
import { deferred } from '@/test/deferred'
import { removeRepo } from './api'
import { cancelPendingInstall, fileActionText, installOptions, planCodeText, suggestedTestCommand, pendingInstall, installBusy, installCancelling, installCancelError } from './factory'

vi.mock('./api', () => ({ removeRepo: vi.fn() }))
afterEach(() => {
  vi.resetAllMocks()
  pendingInstall.value = null
  installBusy.value = false
  installCancelling.value = false
  installCancelError.value = null
})
describe('factory installation state', () => {
  it('copies all four default bindings and keeps the server defaults independent', () => {
    const plan = installPlan()
    const options = installOptions(plan)
    expect(options).toMatchObject({ base: 'main', provider: 'local', backlog_dir: 'backlog', specs_dir: 'specs', docs_dir: 'docs', agents: ['planner', 'builder', 'reviewer', 'documenter'], workflows: ['simple-sdlc'] })
    for (const name of options.agents!) expect(options.bind![name]).toEqual({ harness: 'claude', model: 'sonnet', thinking: 'medium' })
    options.bind!.builder!.thinking = null
    options.agents!.pop()
    expect(plan.bindings!.builder!.thinking).toBe('medium')
    expect(plan.agents).toHaveLength(4)
  })
  it('retains ownership until DELETE succeeds and retries failure', async () => {
    pendingInstall.value = { id: 'temporary', created: true }
    vi.mocked(removeRepo).mockRejectedValueOnce(new Error('delete failed'))
    await cancelPendingInstall()
    expect(pendingInstall.value?.id).toBe('temporary')
    expect(installCancelError.value).toBe('delete failed')
    const deletion = deferred<Awaited<ReturnType<typeof removeRepo>>>()
    vi.mocked(removeRepo).mockReturnValueOnce(deletion.promise)
    const cancelling = cancelPendingInstall()
    expect(pendingInstall.value?.id).toBe('temporary')
    expect(installCancelling.value).toBe(true)
    deletion.resolve({ removed: { id: 'temporary' } } as never)
    await cancelling
    expect(pendingInstall.value).toBeNull()
  })
  it('never removes an existing registration and never cancels an active apply', async () => {
    pendingInstall.value = { id: 'existing', created: false }
    await cancelPendingInstall()
    expect(removeRepo).not.toHaveBeenCalled()
    pendingInstall.value = { id: 'busy', created: true }
    installBusy.value = true
    await cancelPendingInstall()
    expect(pendingInstall.value?.id).toBe('busy')
    expect(removeRepo).not.toHaveBeenCalled()
  })
  it('prefills a given or detected test command, never the installer default', () => {
    expect(installOptions(installPlan({ test_command: { command: 'bun test', source: 'detected', candidates: [], written: true } })).test_command).toBe('bun test')
    expect(suggestedTestCommand(installPlan({ test_command: { command: 'just test', source: 'default' } }))).toBe('')
    expect(suggestedTestCommand(installPlan())).toBe('')
  })
  it('names plan codes and file actions in Czech, unknown ones as they are', () => {
    expect(planCodeText('onboarding_pending')).toBe('onboarding čeká v PR')
    expect(planCodeText('something_new')).toBe('something_new')
    expect(fileActionText('create')).toBe('nový')
  })
})
