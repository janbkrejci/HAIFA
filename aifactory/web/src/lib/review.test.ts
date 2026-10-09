import { afterEach, describe, expect, it, vi } from 'vitest'
import { diffLines, fetchReviews, resolvePr, returnPr } from './review'

function ok(data: unknown) {
  return new Response(JSON.stringify({ ok: true, data, error: null, warnings: [] }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('diffLines', () => {
  it('classifies the lines of a patch', () => {
    const patch = [
      'diff --git a/x b/x',
      'index 1..2 100644',
      '--- a/x',
      '+++ b/x',
      '@@ -1,2 +1,2 @@',
      ' same',
      '-old',
      '+new',
      '--- not a header inside a hunk',
      '\\ No newline at end of file',
      '',
    ].join('\n')
    expect(diffLines(patch).map((l) => l.kind)).toEqual([
      'meta', 'meta', 'meta', 'meta', 'hunk', 'ctx', 'del', 'add', 'del', 'meta',
    ])
  })

  it('returns nothing for an empty patch', () => {
    expect(diffLines('')).toEqual([])
  })
})

describe('review api', () => {
  it('lists the open PRs without a query', async () => {
    const fetchMock = vi.fn(async (_url: string) => ok({ prs: [] }))
    vi.stubGlobal('fetch', fetchMock)
    await fetchReviews()
    expect(fetchMock).toHaveBeenLastCalledWith('/api/repos/haifa/review')
  })

  it('posts return with a note and resolve with an empty body', async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ok({ run: null }))
    vi.stubGlobal('fetch', fetchMock)
    await returnPr('M01-S01-T01', 'přidej test')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/repos/haifa/review/M01-S01-T01/return')
    expect(fetchMock.mock.calls[0][1]?.body).toBe(JSON.stringify({ note: 'přidej test' }))
    await resolvePr('M01-S01-T01')
    expect(fetchMock.mock.calls[1][0]).toBe('/api/repos/haifa/review/M01-S01-T01/resolve')
    expect(fetchMock.mock.calls[1][1]?.body).toBe('{}')
  })
})
