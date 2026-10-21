import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import FailureCard from './FailureCard.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import { failureCard, failureLabel } from '@/lib/failure'
import type { RunSummary } from '@/lib/runs'
import { okResponse, summary } from '@/test/runsFixtures'
import { answerDialog, openDialog } from '@/test/modal'

enableAutoUnmount(afterEach)

// no request leaves the test: a test that expects one stubs fetch itself
beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })))
})

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
  it.each(['continue', 'switch', 'allow'] as const)('shows already_running for %s when another run owns the task', async (action) => {
    const message = 'task M01-S01-T01 is already running: run r-new (pid 123)'
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return new Response(JSON.stringify({
        ok: false, data: null, error: { code: 'already_running', message, issues: [] }, warnings: [],
      }), { status: 409, headers: { 'Content-Type': 'application/json' } })
      return okResponse(action === 'allow'
        ? { run_id: 'r-fail', task_id: 'M01-S01-T01', writes: [], allow: ['README.md'], refused: [] }
        : { run_id: 'r-fail', choices: [{ harness: 'claude', model: 'model', thinking: null }] })
    }))
    const wrapper = card({ failure_kind: action === 'allow' ? 'writes_violation' : 'quota', failure_detail: { harness: 'codex', paths: ['README.md'] } })
    await flushPromises()
    if (action === 'allow') {
      await wrapper.get('[data-test="allow-writes"]').trigger('click')
      await answerDialog(true)
    } else {
      await wrapper.get(`[data-test="${action === 'switch' ? 'switch-harness' : 'retry-run'}"]`).trigger('click')
      await flushPromises()
      await wrapper.get(`[data-test="${action === 'switch' ? 'switch-form' : 'retry-form'}"]`).trigger('submit')
    }
    await flushPromises()
    expect(wrapper.get(`[data-test="${action === 'allow' ? 'allow-error' : action === 'switch' ? 'switch-error' : 'retry-error'}"]`).text()).toContain(message)
    expect(wrapper.emitted('retried')).toBeUndefined()
  })

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

  it('nothing_to_do: the agent and its summary, Hotovo and Zrušit task', () => {
    const wrapper = card({
      error: "builder reported status='fail': vše už je hotové",
      failure_kind: 'nothing_to_do',
      failure_detail: { agent: 'builder', summary: 'vše už je hotové v HEAD', fail_kind: 'nothing_to_do' },
    })
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Agent neměl co dělat')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Agent builder neměl co dělat: vše už je hotové v HEAD.')
    expect(actions(wrapper)).toEqual(['Hotovo', 'Zrušit task'])
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
    expect(actions(wrapper)).toEqual(['Pokračovat s jiným harnessem', 'Pokračovat', 'Zrušit task'])
  })

  it('quota: „Pokračovat s jiným harnessem“ offers the tested harnesses and retries on one', async () => {
    const choices = {
      run_id: 'r-fail',
      exhausted: { harness: 'codex', model: 'gpt-6.1-sol' },
      choices: [
        { harness: 'claude', model: 'claude-opus-5-5', thinking: 'high' },
        { harness: 'pi', model: 'x/y', thinking: null },
      ],
    }
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? okResponse({ task_id: 'M01-S01-T01', action: 'retry', run: null, pending: true })
        : okResponse(choices),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({ error: 'codex: quota exhausted', failure_kind: 'quota', failure_detail: { harness: 'codex' } })
    expect(fetchMock).not.toHaveBeenCalled()
    await wrapper.get('[data-test="switch-harness"]').trigger('click')
    await flushPromises()
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/runs\/r-fail\/harness-choices$/)
    const select = wrapper.getComponent(SelectMenu)
    expect(select.props('options').map((o: { label: string }) => o.label)).toEqual([
      'claude · claude-opus-5-5 · high',
      'pi · x/y',
    ])
    expect(select.props('modelValue')).toBe('claude')
    select.vm.$emit('update:modelValue', 'pi')
    await flushPromises()
    await wrapper.get('[data-test="switch-form"]').trigger('submit')
    await flushPromises()
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/runs\/r-fail\/retry$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(String(init.body))).toEqual({ harness: 'pi' })
    expect(wrapper.emitted('retried')).toHaveLength(1)
  })

  it('quota without another tested harness says so', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => okResponse({ run_id: 'r-fail', exhausted: { harness: 'codex', model: null }, choices: [] })))
    const wrapper = card({ error: 'codex: quota exhausted', failure_kind: 'quota', failure_detail: { harness: 'codex' } })
    await wrapper.get('[data-test="switch-harness"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-test="switch-none"]').text()).toContain('Žádný jiný harness')
    expect(wrapper.find('[data-test="switch-submit"]').exists()).toBe(false)
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

  it('blocked: its own colour, the blocking tasks as links, Pokračovat and Zrušit task', () => {
    const wrapper = card({
      error: 'blocked: task M01-S01-T01 waits for M01-TODO-T01, M01-TODO-T02',
      failure_kind: 'blocked',
      failure_detail: { blockers: ['M01-TODO-T01', 'M01-TODO-T02'] },
    })
    expect(wrapper.get('[data-test="failure-card"]').attributes('data-kind')).toBe('blocked')
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Blokovaný')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe(
      'Task čeká na blokující tasky M01-TODO-T01, M01-TODO-T02; po jejich dokončení se dá pokračovat.',
    )
    const links = wrapper.findAll('[data-fact="blockers"] [data-test="blocker-link"]')
    expect(links.map((a) => a.text())).toEqual(['M01-TODO-T01', 'M01-TODO-T02'])
    expect(links[0]?.attributes('href')).toContain('/backlog/M01-TODO-T01')
    expect(actions(wrapper)).toEqual(['Pokračovat', 'Zrušit task'])
  })

  it('blocked of an older run: the kind and the blockers from its error', () => {
    const run = { state: 'failed', error: 'blocked: task A-T01 waits for B-T01; boom' }
    expect(failureCard(run)?.kind).toBe('blocked')
    expect(failureCard(run)?.facts[0]?.items).toEqual(['B-T01'])
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

  it('nothing_to_do: Hotovo marks the task done without changes after a confirmation', async () => {
    const fetchMock = vi.fn(async () => okResponse({ task_id: 'M01-S01-T01', commit: {}, run: summary({}) }))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({
      error: "builder reported status='fail': jen front matter",
      failure_kind: 'nothing_to_do',
      failure_detail: { agent: 'builder', summary: 'zadání žádá jen změnu front matter', fail_kind: 'nothing_to_do' },
    })
    await wrapper.get('[data-test="mark-done"]').trigger('click')
    await flushPromises()
    expect(openDialog()?.textContent).toContain('Označit task M01-S01-T01 jako hotový?')
    await answerDialog(false)
    expect(fetchMock).not.toHaveBeenCalled()
    await wrapper.get('[data-test="mark-done"]').trigger('click')
    await answerDialog(true)
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/runs\/r-fail\/done$/)
    expect(init.method).toBe('POST')
    expect(wrapper.emitted('done')).toHaveLength(1)
    expect(wrapper.get('[data-test="mark-done-done"]').text()).toBe('Task M01-S01-T01 je hotový bez změn.')
    expect(wrapper.get('[data-test="mark-done"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-test="cancel-task"]').attributes('disabled')).toBeDefined()
  })

  it('nothing_to_do: a refused Hotovo shows the error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify({ ok: false, error: { code: 'not_nothing_to_do', message: 'not nothing_to_do' } }), { status: 409 })),
    )
    const wrapper = card({ error: 'x', failure_kind: 'nothing_to_do', failure_detail: { agent: 'builder', summary: 's' } })
    await wrapper.get('[data-test="mark-done"]').trigger('click')
    await answerDialog(true)
    await flushPromises()
    expect(wrapper.get('[data-test="mark-done-error"]').text()).toContain('Task se nepodařilo označit jako hotový')
    expect(wrapper.emitted('done')).toBeUndefined()
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

  it('writes_violation: Povolit tyto cesty a pokračovat adds the paths and retries', async () => {
    const plan = {
      run_id: 'r-fail',
      task_id: 'M01-S01-T01',
      writes: ['src/app/'],
      allow: ['README.md'],
      refused: [
        { path: '.factory/config.yaml', reason: 'protected', message: 'a protected path' },
        { path: 'notes.md', reason: 'main_checkout', message: 'main checkout' },
      ],
    }
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? okResponse({ task_id: 'M01-S01-T01', action: 'retry', run: null, pending: true, allow_writes: { ...plan, new_writes: ['src/app/', 'README.md'] } })
        : okResponse(plan),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({
      error: 'builder changed paths outside its task run',
      failure_kind: 'writes_violation',
      failure_detail: { agent: 'builder', paths: ['README.md', '.factory/config.yaml'], main_paths: ['notes.md'], writes: ['src/app/'] },
    })
    await flushPromises()
    expect(String(fetchMock.mock.calls[0]?.[0])).toMatch(/\/runs\/r-fail\/allow-writes$/)
    expect(fact(wrapper, 'paths')).toEqual(['README.md', '.factory/config.yaml', 'hlavní checkout: notes.md'])
    expect(actions(wrapper)).toEqual(['Povolit tyto cesty a pokračovat', 'Pokračovat', 'Zrušit task'])
    expect(fact(wrapper, 'allow')).toEqual(['README.md'])
    expect(fact(wrapper, 'refused')).toEqual([
      '.factory/config.yaml — chráněná cesta (protected_files), writes ji nepovolí',
      'notes.md — zápis do hlavního checkoutu mimo worktree běhu, writes ho nepovolí',
    ])
    await wrapper.get('[data-test="allow-writes"]').trigger('click')
    expect(openDialog()?.textContent).toContain('Do writes tasku přibude README.md')
    await answerDialog(true)
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/runs\/r-fail\/allow-writes$/)
    expect(init.method).toBe('POST')
    expect(wrapper.emitted('retried')).toHaveLength(1)
    expect(wrapper.get('[data-test="allow-done"]').text()).toContain('Writes tasku M01-S01-T01 rozšířené')
  })

  it('writes_needed: the paths with reasons and Povolit tyto cesty a pokračovat', async () => {
    const plan = { run_id: 'r-fail', task_id: 'M01-S01-T01', writes: ['src/app/'], allow: ['tests/e2e/test_x.py'], refused: [] }
    const fetchMock = vi.fn(async (_url: string, init?: RequestInit) =>
      init?.method === 'POST'
        ? okResponse({ task_id: 'M01-S01-T01', action: 'retry', run: null, pending: true, allow_writes: { ...plan, new_writes: ['src/app/', 'tests/e2e/test_x.py'] } })
        : okResponse(plan),
    )
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = card({
      error: "builder reported status='fail': review needs a browser test",
      failure_kind: 'writes_needed',
      failure_detail: {
        agent: 'builder',
        summary: 'review needs a browser test',
        fail_kind: 'needs_writes',
        paths: ['tests/e2e/test_x.py'],
        needs_writes: [{ path: 'tests/e2e/test_x.py', reason: 'the browser test the review requires' }],
      },
    })
    await flushPromises()
    expect(wrapper.get('[data-test="failure-kind"]').text()).toBe('Chybí cesty ve writes')
    expect(wrapper.get('[data-test="failure-sentence"]').text()).toBe('Agent builder potřebuje změnit cesty mimo writes tasku (1 cesta).')
    expect(fact(wrapper, 'paths')).toEqual(['tests/e2e/test_x.py — the browser test the review requires'])
    expect(actions(wrapper)).toEqual(['Povolit tyto cesty a pokračovat', 'Pokračovat', 'Zrušit task'])
    expect(fact(wrapper, 'allow')).toEqual(['tests/e2e/test_x.py'])
    await wrapper.get('[data-test="allow-writes"]').trigger('click')
    await answerDialog(true)
    const [url, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit]
    expect(url).toMatch(/\/runs\/r-fail\/allow-writes$/)
    expect(init.method).toBe('POST')
    expect(wrapper.emitted('retried')).toHaveLength(1)
  })

  it('writes_needed of a ci-fix run: allow and approve again, no Pokračovat', async () => {
    const plan = { run_id: 'r-fail', task_id: 'M01-S01-T01', writes: ['src/app/'], allow: ['src/skill/codes.py'], refused: [] }
    vi.stubGlobal('fetch', vi.fn(async () => okResponse(plan)))
    const wrapper = card({
      workflow: 'ci-fix',
      error: "builder reported status='fail': needs codes.py",
      failure_kind: 'writes_needed',
      failure_detail: { agent: 'builder', paths: ['src/skill/codes.py'] },
    })
    await flushPromises()
    expect(fact(wrapper, 'paths')).toEqual(['src/skill/codes.py'])
    expect(actions(wrapper)).toEqual(['Povolit tyto cesty a schválit znovu', 'Zrušit task'])
    await wrapper.get('[data-test="allow-writes"]').trigger('click')
    expect(openDialog()?.textContent).toContain('schválení PR se spustí znovu')
  })

  it('writes_violation with nothing writes can allow: no action, the reasons', async () => {
    const plan = {
      run_id: 'r-fail',
      task_id: 'M01-S01-T01',
      writes: ['src/app/'],
      allow: [],
      refused: [{ path: 'backlog/x.md', reason: 'backlog', message: 'a backlog path' }],
    }
    vi.stubGlobal('fetch', vi.fn(async () => okResponse(plan)))
    const wrapper = card({
      error: 'builder changed paths outside its task run',
      failure_kind: 'writes_violation',
      failure_detail: { agent: 'builder', paths: ['backlog/x.md'], writes: ['src/app/'] },
    })
    await flushPromises()
    expect(actions(wrapper)).toEqual(['Pokračovat', 'Zrušit task'])
    expect(fact(wrapper, 'refused')).toEqual(['backlog/x.md — cesta v backlogu, backlog zapisuje jen factory'])
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
