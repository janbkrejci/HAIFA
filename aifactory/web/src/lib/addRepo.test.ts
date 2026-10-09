import { describe, expect, it } from 'vitest'
import type { FsEntry } from './api'
import { PROBLEM_TEXT, expandHome, filterEntries, problemText, splitForSuggest } from './addRepo'

function entry(name: string): FsEntry {
  return { name, path: `/home/me/${name}`, is_git: false, has_factory: false }
}

describe('expandHome', () => {
  it('expands ~ and ~/ only', () => {
    expect(expandHome('~', '/home/me')).toBe('/home/me')
    expect(expandHome('~/', '/home/me')).toBe('/home/me/')
    expect(expandHome('~/code/x', '/home/me/')).toBe('/home/me/code/x')
    expect(expandHome('/abs/~/x', '/home/me')).toBe('/abs/~/x')
    expect(expandHome('~other/x', '/home/me')).toBe('~other/x')
  })
})

describe('splitForSuggest', () => {
  it('splits after the last slash', () => {
    expect(splitForSuggest('~/co')).toEqual({ dir: '~/', prefix: 'co' })
    expect(splitForSuggest('/Users/a/')).toEqual({ dir: '/Users/a/', prefix: '' })
    expect(splitForSuggest('/Users/a/b')).toEqual({ dir: '/Users/a/', prefix: 'b' })
    expect(splitForSuggest('code')).toBeNull()
  })
})

describe('filterEntries', () => {
  it('keeps the server order, ignores case and limits', () => {
    const entries = [entry('Code'), entry('docs'), entry('cobol'), entry('x')]
    expect(filterEntries(entries, 'co').map((e) => e.name)).toEqual(['Code', 'cobol'])
    expect(filterEntries(entries, '').map((e) => e.name)).toEqual(['Code', 'docs', 'cobol', 'x'])
    expect(filterEntries(entries, '', 2)).toHaveLength(2)
  })
})

describe('problemText', () => {
  it('has a reason for every known code and the server message otherwise', () => {
    expect(problemText({ code: 'not_git', message: 'x' })).toContain('HAIFA nespouští git init')
    expect(problemText({ code: 'linked_worktree', message: 'x', main_checkout: '/w/main' })).toContain('/w/main')
    expect(problemText({ code: 'weird', message: 'server says' })).toBe('server says')
    expect(Object.keys(PROBLEM_TEXT).sort()).toEqual(
      ['bare_repo', 'linked_worktree', 'no_commits', 'not_a_directory', 'not_git', 'path_not_found', 'run_worktree', 'trace_db_shared'],
    )
  })
})
