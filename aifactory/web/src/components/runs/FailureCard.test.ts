import { afterEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import FailureCard from './FailureCard.vue'
import { failureCard, failureLabel } from '@/lib/failure'
import type { RunSummary } from '@/lib/runs'
import { okResponse, summary } from '@/test/runsFixtures'
import { answerDialog, openDialog } from '@/test/modal'

enableAutoUnmount(afterEach)

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

function failed(over: Partial<RunSummary>): RunSummary {
  return summary({ run_id: 'r-fail', state: 'failed', pr: null, ...over })
}

function card(over: Partial<RunSummary>, phases: { status: string; harness?: string; model?: string }[] = []) {
  return mount(FailureCard, { props: { run: failed(over), phases }, attachTo: document.body })
}

function fact(wrapper: VueWrapper, id: string): string[] {
  return wrapper.findAll(`[data-fact="${id}"] [data-test="failure-item"]`).map((li) => li.text())
}

function actions(wrapper: VueWrapper): string[] {
  return wrapper.findAll('.actions button').map((b) => b.text())
}

describe('FailureCard', () => {
  it('accept_not_met: the error sentence, review objections, failed checks and the accept values', () => {
    const wrapper = card({
      error: 'Review neschválilo ani po 2 kolech: chybí test pro prázdný vstup',
      failure_kind: 'accept_not_met',
      failure_detail: {
        accept: 'review.approved and test.passed',
        accepted: false,
        exit_code: 0,
        values: { 'review.approved': false, 'test.passed': true },
        rounds: [{ loop: 'fix', until: 'review.approved', rounds: 2, max: 2 }],
        review: { step: 'review', summary: 'needs work', objections: ['chybí test pro prázdný vstup', 'README není česky'] },
        test: { step: 'test', summary: 'red', failed_checks: ['pytest exited 1\nFAILED test_x'] },
      },
    })
    expect(wrapper.get('[data-test="failure-card"]').attributes('data-kind')).toBe('accept_not_met')
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Nesplněná podmínka accept')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe(
      'Review neschválilo ani po 2 kolech: chybí test pro prázdný vstup.',
    )
    expect(wrapper.get('[data-fact="objections"] h4').text()).toBe('Výtky review (review)')
    expect(fact(wrapper, 'objections')).toEqual(['chybí test pro prázdný vstup', 'README není česky'])
    expect(fact(wrapper, 'checks')).toEqual(['pytest exited 1\nFAILED test_x'])
    expect(fact(wrapper, 'accept')).toEqual(['review.approved and test.passed'])
    expect(fact(wrapper, 'values')).toEqual(['review.approved = false', 'test.passed = true'])
    expect(fact(wrapper, 'rounds')).toEqual(['fix: 2 z 2'])
    expect(actions(wrapper)).toEqual(['Pokračovat', 'Zrušit task'])
    // the sentence is the error: no second copy of it
    expect(wrapper.find('[data-test="run-error"]').exists()).toBe(false)
  })

  it('accept_not_met of an older run: the accept expression instead of "accept not met"', () => {
    const wrapper = card({
      error: 'accept not met',
      failure_kind: 'accept_not_met',
      failure_detail: { accept: 'review.approved', accepted: false, exit_code: 0 },
    })
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Podmínka accept `review.approved` nebyla splněna.')
  })

  it('nothing_to_do: the agent and its summary, only Zrušit task', () => {
    const wrapper = card({
      error: "builder reported status='fail': vše už je hotové",
      failure_kind: 'nothing_to_do',
      failure_detail: { agent: 'builder', summary: 'vše už je hotové v HEAD', fail_kind: 'nothing_to_do' },
    })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Agent neměl co dělat')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Agent builder neměl co dělat: vše už je hotové v HEAD.')
    expect(actions(wrapper)).toEqual(['Zrušit task'])
  })

  it('quota: the harness, the model and its message', () => {
    const wrapper = card({
      error: 'claude: quota exhausted: You have hit your limit',
      failure_kind: 'quota',
      failure_detail: { harness: 'claude', message: 'You have hit your limit · resets 3pm', agent: 'builder', model: 'claude-opus-5-5' },
    })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Vyčerpaná kvóta')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe(
      'Harness claude ohlásil vyčerpanou kvótu u modelu claude-opus-5-5 (agent builder).',
    )
    expect(fact(wrapper, 'harness')).toEqual(['claude'])
    expect(fact(wrapper, 'model')).toEqual(['claude-opus-5-5'])
    expect(fact(wrapper, 'message')).toEqual(['You have hit your limit · resets 3pm'])
    expect(actions(wrapper)).toEqual(['Pokračovat', 'Zrušit task'])
  })

  it('quota recorded without a model: the model of the phase that failed', () => {
    const wrapper = card(
      { error: 'codex: quota exhausted', failure_kind: 'quota', failure_detail: { harness: 'codex', message: 'usage limit' } },
      [
        { status: 'success', harness: 'claude', model: 'sonnet' },
        { status: 'fail', harness: 'codex', model: 'gpt-5.5' },
      ],
    )
    expect(fact(wrapper, 'model')).toEqual(['gpt-5.5'])
  })

  it('writes_violation: the paths outside writes and the writes allowed', () => {
    const wrapper = card({
      error: 'builder is task-scoped but modified 2 path(s)',
      failure_kind: 'writes_violation',
      failure_detail: { agent: 'builder', paths: ['README.md', 'docs/x.md'], writes: ['aifactory/', 'justfile'] },
    })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Zápis mimo writes')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Agent builder zapsal mimo povolené cesty (2 cesty).')
    expect(fact(wrapper, 'paths')).toEqual(['README.md', 'docs/x.md'])
    expect(fact(wrapper, 'writes')).toEqual(['aifactory/', 'justfile'])
    expect(wrapper.get('[data-fact="paths"] ul').classes()).toContain('mono')
    // the whole error says more than the sentence
    expect(wrapper.get('[data-test="run-error"]').text()).toBe('builder is task-scoped but modified 2 path(s)')
  })

  it('writes_violation of the task run guard: its problems', () => {
    const wrapper = card({
      error: 'builder changed paths outside its task run',
      failure_kind: 'writes_violation',
      failure_detail: { agent: 'builder', problems: ['main checkout: a.md — restored'], writes: ['aifactory/'] },
    })
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Agent builder zapsal mimo povolené cesty (1 cesta).')
    expect(fact(wrapper, 'paths')).toEqual(['main checkout: a.md — restored'])
  })

  it('invalid_output: invalid JSON and gates still red', () => {
    const json = card({
      error: 'builder never produced valid BuildOutput JSON',
      failure_kind: 'invalid_output',
      failure_detail: { agent: 'builder', cause: 'json', output_type: 'BuildOutput', error: 'Expecting value: line 1' },
    })
    expect(json.get('[data-test="failure-kind"]').text()).toBe('Neplatný výstup agenta')
    expect(json.get('[data-test="failure-sentence"]').text()).toBe('Agent builder nevrátil platný JSON BuildOutput.')
    expect(fact(json, 'error')).toEqual(['Expecting value: line 1'])
    const gates = card({
      error: 'reviewer failed gates after 3 attempt(s)',
      failure_kind: 'invalid_output',
      failure_detail: { agent: 'reviewer', cause: 'gates', violations: ['claims tests pass, they fail'] },
    })
    expect(gates.get('[data-test="failure-sentence"]').text()).toBe('Výstup agenta reviewer neprošel kontrolami ani po opravách.')
    expect(fact(gates, 'violations')).toEqual(['claims tests pass, they fail'])
  })

  it('process_gone: the PID of the process', () => {
    const wrapper = card({ state: 'aborted', error: 'process 4242 is gone', failure_kind: 'process_gone', failure_detail: { pid: 4242 } })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Proces běhu skončil')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Proces běhu (PID 4242) skončil dřív, než běh doběhl.')
    expect(actions(wrapper)).toEqual(['Pokračovat', 'Zrušit task'])
  })

  it('stopped: the operator note, Ctrl+C or the signal', () => {
    const note = card({ state: 'stopped', error: 'stopped from the dashboard', failure_kind: 'stopped', failure_detail: { note: 'stopped from the dashboard' } })
    expect(note.get('[data-test="failure-kind"]').text()).toBe('Běh zastaven')
    expect(note.get('[data-test="failure-sentence"]').text()).toBe('Běh zastavil operátor: stopped from the dashboard.')
    const signal = card({ error: 'interrupted: SystemExit(143)', failure_kind: 'stopped', failure_detail: { cause: 'signal', signal: 15 } })
    expect(signal.get('[data-test="failure-sentence"]').text()).toBe('Proces běhu ukončil signál 15.')
    const ctrlc = card({ error: 'interrupted', failure_kind: 'stopped', failure_detail: { cause: 'keyboard_interrupt' } })
    expect(ctrlc.get('[data-test="failure-sentence"]').text()).toBe('Proces běhu přerušil Ctrl+C.')
  })

  it('other: the first line of the error, the whole error below', () => {
    const wrapper = card({ error: 'worktree add failed\nfatal: branch exists', failure_kind: 'other', failure_detail: { cause: 'worktree' } })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Jiná chyba')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('worktree add failed.')
    expect(wrapper.get('[data-test="run-error"]').text()).toBe('worktree add failed\nfatal: branch exists')
  })

  it('shows nothing for a succeeded or running run; an older failed run reads as other', () => {
    expect(card({ state: 'succeeded', error: null }).find('[data-test="failure-card"]').exists()).toBe(false)
    expect(card({ state: 'running', error: null }).find('[data-test="failure-card"]').exists()).toBe(false)
    expect(failureCard({ state: 'failed', error: 'boom' })?.kind).toBe('other')
    expect(failureLabel('something_new')).toBe('something_new')
    expect(failureLabel(null)).toBe('')
  })

  it('Pokračovat retries the run with a note', async () => {
    const fetchMock = vi.fn(async () => okResponse({ task_id: 'M01-S01-T01', action: 'retry', run: null, pending: true }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({ error: 'Review neschválilo', failure_kind: 'accept_not_met', failure_detail: {} })
    await wrapper.get('[data-test="retry-run"]').trigger('click')
    await wrapper.get('[data-test="retry-note"]').setValue('oprav README')
    await wrapper.get('[data-test="retry-form"]').trigger('submit')
    await flushPromises()
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/runs\/r-fail\/retry$/)
    expect(JSON.parse(String(init.body))).toEqual({ note: 'oprav README' })
    expect(wrapper.emitted('retried')).toHaveLength(1)
  })

  it('Zrušit task cancels the task after a confirmation', async () => {
    const fetchMock = vi.fn(async () => okResponse({ task_id: 'M01-S01-T01' }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({ error: 'boom', failure_kind: 'other', failure_detail: {} })
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    await flushPromises()
    expect(openDialog()?.textContent).toContain('Zrušit task M01-S01-T01?')
    await answerDialog(false)
    expect(fetchMock).not.toHaveBeenCalled()
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    await answerDialog(true)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/backlog\/tasks\/M01-S01-T01\/edit$/)
    expect(JSON.parse(String(init.body))).toEqual({ status: 'cancelled' })
    expect(wrapper.emitted('cancelled')).toHaveLength(1)
    expect(wrapper.get('[data-test="cancel-done"]').text()).toBe('Task M01-S01-T01 je zrušený.')
    expect(wrapper.get('[data-test="cancel-task"]').attributes('disabled')).toBeDefined()
  })

  it('says why the task could not be cancelled', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ ok: false, data: null, error: { code: 'invalid_status', message: 'task is done' }, warnings: [] }), { status: 400 })))
    const wrapper = card({ error: 'boom', failure_kind: 'other', failure_detail: {} })
    await wrapper.get('[data-test="cancel-task"]').trigger('click')
    await answerDialog(true)
    expect(wrapper.get('[data-test="cancel-error"]').text()).toContain('Task se nepodařilo zrušit')
    expect(wrapper.emitted('cancelled')).toBeUndefined()
  })
})
