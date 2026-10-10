import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  ApiError,
  DB_BUSY_MESSAGE,
  addRepo,
  fetchFactoryCheck,
  removeRepo,
  apiBase,
  fetchHealth,
  fetchRepos,
  getApi,
  getGlobal,
  isDbBusy,
  isDbBusyText,
  postApi,
  postGlobal,
} from './api'

function stubFetch(body: unknown, status = 200) {
  const fetchMock = vi.fn(async () => new Response(JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('api', () => {
  it('returns data of an ok envelope', async () => {
    const fetchMock = stubFetch({
      ok: true,
      data: { app: 'haifa-dashboard', version: '0.1.0', home: '/home/.haifa' },
      error: null,
      warnings: [],
    })
    await expect(fetchHealth()).resolves.toEqual({ app: 'haifa-dashboard', version: '0.1.0', home: '/home/.haifa' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health')
  })

  it('sends repo requests to the repo in the URL', async () => {
    const fetchMock = stubFetch({ ok: true, data: { items: [] }, error: null, warnings: [] })
    expect(apiBase()).toBe('/api/repos/haifa')
    await getApi('/backlog')
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/backlog')
    window.location.hash = '#/r/my%20repo/runs'
    await getApi('/runs')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/my%20repo/runs')
  })

  it('sends nothing without a repo in the URL', async () => {
    const fetchMock = stubFetch({ ok: true, data: {}, error: null, warnings: [] })
    window.location.hash = '#/overview'
    await expect(getApi('/backlog')).rejects.toMatchObject({ code: 'no_repo' })
    await expect(postApi('/backlog/commit')).rejects.toMatchObject({ code: 'no_repo' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends global requests without a repo', async () => {
    const fetchMock = stubFetch({ ok: true, data: { repos: [], home: '/h' }, error: null, warnings: [] })
    window.location.hash = '#/overview'
    await expect(getGlobal('/health')).resolves.toEqual({ repos: [], home: '/h' })
    expect(fetchMock).toHaveBeenCalledWith('/api/health')
    await expect(fetchRepos()).resolves.toEqual({ repos: [], home: '/h' })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos')
    await postGlobal('/restart')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/restart', { method: 'POST' })
  })

  it('throws ApiError with the error code', async () => {
    stubFetch(
      {
        ok: false,
        data: null,
        error: { code: 'not_found', message: 'no API endpoint', path: null, id: null, issues: [] },
        warnings: [],
      },
      404,
    )
    const promise = getApi('/nope')
    await expect(promise).rejects.toBeInstanceOf(ApiError)
    await expect(getApi('/nope')).rejects.toMatchObject({ code: 'not_found' })
  })
})

describe('postApi', () => {
  it('posts and returns data', async () => {
    const fetchMock = stubFetch({ ok: true, data: { done: true }, error: null, warnings: [] })
    await expect(postApi('/runs/r1/stop')).resolves.toEqual({ done: true })
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/runs/r1/stop', { method: 'POST' })
  })

  it('sends a JSON body', async () => {
    const fetchMock = stubFetch({ ok: true, data: {}, error: null, warnings: [] })
    await postApi('/x', { a: 1 })
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/x', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: '{"a":1}',
    })
  })

  it('throws ApiError with the error code', async () => {
    stubFetch(
      {
        ok: false,
        data: null,
        error: { code: 'run_not_running', message: 'is failed', path: null, id: null, issues: [] },
        warnings: [],
      },
      409,
    )
    await expect(postApi('/runs/r1/stop')).rejects.toMatchObject({
      code: 'run_not_running',
      message: 'is failed',
    })
  })

  it('carries the validation issues of the envelope', async () => {
    const issue = { code: 'unknown_ref', message: 'unknown id NOPE', path: 'backlog/a.md', id: 'T1' }
    stubFetch(
      {
        ok: false,
        data: null,
        error: { code: 'backlog_invalid', message: 'rejected', path: null, id: null, issues: [issue] },
        warnings: [],
      },
      422,
    )
    const error = await postApi('/backlog/tasks', {}).catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect((error as ApiError).issues).toEqual([issue])
  })

  it('defaults to no issues', () => {
    expect(new ApiError('x', 'y').issues).toEqual([])
  })
})

describe('busy trace DB', () => {
  it('replaces the raw lock error with a plain message', async () => {
    stubFetch(
      {
        ok: false,
        data: null,
        error: { code: 'trace_db_locked', message: 'database is locked', path: null, id: null, issues: [] },
        warnings: [],
      },
      503,
    )
    const error = await getApi('/runs').catch((e: unknown) => e)
    expect(isDbBusy(error)).toBe(true)
    expect((error as ApiError).message).toBe(DB_BUSY_MESSAGE)
    expect(isDbBusyText(`Běhy se nepodařilo načíst: ${(error as ApiError).message}`)).toBe(true)
  })

  it('leaves other errors alone', () => {
    expect(isDbBusy(new ApiError('conflict', 'x'))).toBe(false)
    expect(isDbBusyText('database is locked')).toBe(false)
    expect(isDbBusyText(null)).toBe(false)
  })
})

describe('repos and the Factory tab', () => {
  it('returns the check report of a checks_failed envelope', async () => {
    const report = { ok: false, findings: [], counts: { error: 1, warning: 0, info: 0 } }
    const fetchMock = stubFetch({
      ok: false,
      data: report,
      error: { code: 'checks_failed', message: '1 error(s)', path: null, id: null, issues: [] },
      warnings: [],
    })
    await expect(fetchFactoryCheck()).resolves.toEqual(report)
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/haifa/factory/check')
    await fetchFactoryCheck({ fresh: true })
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/factory/check?fresh=1')
  })

  it('throws other errors of the check', async () => {
    stubFetch(
      {
        ok: false,
        data: null,
        error: { code: 'not_a_repository', message: 'no repo', path: null, id: null, issues: [] },
        warnings: [],
      },
      422,
    )
    await expect(fetchFactoryCheck()).rejects.toMatchObject({ code: 'not_a_repository' })
  })

  it('removes a repo with DELETE /api/repos/<id>', async () => {
    const fetchMock = stubFetch({ ok: true, data: { removed: { id: 'a b' } }, error: null, warnings: [] })
    await removeRepo('a b')
    expect(fetchMock).toHaveBeenCalledWith('/api/repos/a%20b', { method: 'DELETE' })
  })

  it('keeps the data of a failed envelope on the error', async () => {
    stubFetch(
      {
        ok: false,
        data: { repo: 'other' },
        error: { code: 'trace_db_shared', message: 'shared', path: null, id: null, issues: [] },
        warnings: [],
      },
      409,
    )
    await expect(addRepo('/w/x')).rejects.toMatchObject({ code: 'trace_db_shared', data: { repo: 'other' } })
  })
})


describe('factory plan and apply choices', () => {
  it('whitelists update/config choices and drops Azure when provider changes', async () => {
    const { factoryChoices } = await import('./api')
    const injected = { take: ['agent/builder'], merge: [], migrate: ['m1'], base: 'main', provider: 'local', azure: { organization: 'org', project: 'project', repository: 'repo' }, content: 'forbidden', files: ['forbidden'], path: 'forbidden', test_command: 'just check' }
    expect(factoryChoices('update', injected)).toEqual({ take: ['agent/builder'], merge: [], migrate: ['m1'] })
    expect(factoryChoices('config_commit', injected)).toEqual({})
    expect(factoryChoices('init', injected).azure).toBeUndefined()
    expect(factoryChoices('init', { ...injected, provider: 'azure' }).azure).toEqual(injected.azure)
    expect('test_command' in factoryChoices('init', injected)).toBe(false)
  })
  it('previews and saves a roster change of the given repo', async () => {
    const { saveFactoryRoster } = await import('./api')
    const fetchMock = stubFetch({ ok: true, data: { agents: [], before: [], diff: '', changed: false }, error: null, warnings: [] })
    await saveFactoryRoster({ preset: 'codex', dry_run: true }, 'repo id')
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/repo%20id/factory/roster', expect.objectContaining({ method: 'POST', body: JSON.stringify({ preset: 'codex', dry_run: true }) }))
  })
  it('preserves envelope-only warnings in pull previews and results', async () => {
    const { fetchBasePullPlan, applyBasePull } = await import('./api')
    const fetchMock = stubFetch({ ok: true, data: { action: 'pull', before: 'old', after: 'new' }, error: null, warnings: ['remote warning'] })
    expect((await fetchBasePullPlan('other')).envelopeWarnings).toEqual(['remote warning'])
    expect((await applyBasePull('reviewed-digest', 'other')).warnings).toEqual(['remote warning'])
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/other/config/pull', expect.objectContaining({ body: JSON.stringify({ digest: 'reviewed-digest' }) }))
  })
  it('serializes only choices, target, message and digest for an explicit repo', async () => {
    const { fetchFactoryPlan, applyFactoryPlan } = await import('./api')
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify({ ok: true, data: { digest: 'd', files: [], blockers: [] }, error: null, warnings: ['directory has foreign content'] })))
    vi.stubGlobal('fetch', fetchMock)
    const options = { base: 'main', provider: 'local', agents: ['builder'], bind: { builder: { harness: 'codex', model: 'gpt-6.1-sol', thinking: 'medium', content: 'injected' } }, files: ['injected'], content: 'injected', path: 'injected', azure: { organization: 'unused', project: '', repository: '' } }
    const plan = await fetchFactoryPlan({ action: 'init', options, target: 'base' }, 'repo id')
    expect(plan.envelopeWarnings).toEqual(['directory has foreign content'])
    await applyFactoryPlan({ action: 'init', options, target: 'pr', digest: 'd', message: 'install' }, 'repo id')
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(['/api/repos/repo%20id/factory/plan', '/api/repos/repo%20id/factory/apply'])
    const body = JSON.parse(String((fetchMock.mock.calls[1] as unknown as [string, RequestInit])[1].body))
    expect(body).toEqual({ action: 'init', target: 'pr', digest: 'd', message: 'install', options: { base: 'main', provider: 'local', agents: ['builder'], bind: { builder: { harness: 'codex', model: 'gpt-6.1-sol', thinking: 'medium' } } } })
    vi.unstubAllGlobals()
  })
})
