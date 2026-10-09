import { describe, expect, it } from 'vitest'
import type { CheckFinding, MachineCheck, RepoItem } from './api'
import { focusRepo, gettingStartedSteps, nextStep, type GettingStartedInput } from './gettingStarted'
import { detectedHarnesses } from './roster'

function check(ok = true, findings: Partial<CheckFinding>[] = []): MachineCheck {
  return {
    ok, checked_at: 'now', cached: false, harness_repos: { claude: 0, codex: 0, pi: 0 },
    findings: findings.map((f) => ({ code: 'x', scope: 'machine', severity: 'info', message: '', fix: null, action: null, ...f })),
  }
}

function repo(id: string, status: RepoItem['status']): RepoItem {
  return { id, name: id.toUpperCase(), path: `/w/${id}`, added_at: '', status, factory: null }
}

const MISSING = ['codex', 'pi'].map((name) => ({ code: 'harness_missing', message: `harness ${name} (${name}) is not installed` }))

function input(extra: Partial<GettingStartedInput> = {}): GettingStartedInput {
  return { check: check(true, MISSING), library: { exists: true }, repos: [repo('a', 'ok')], rosterAgents: 4, projects: 1, ...extra }
}

const done = (i: GettingStartedInput) => Object.fromEntries(gettingStartedSteps(i).map((s) => [s.id, s.done]))

describe('gettingStartedSteps', () => {
  it('is all done for a checked machine, a library, an installed repo with a roster and a project', () => {
    const steps = gettingStartedSteps(input())
    expect(steps.map((s) => s.id)).toEqual(['machine', 'library', 'harnesses', 'repo', 'factory', 'roster', 'project'])
    expect(steps.every((s) => s.done)).toBe(true)
    expect(nextStep(steps)).toBeNull()
    expect(steps.find((s) => s.id === 'harnesses')?.hint).toBe('Přihlášené: claude.')
  })

  it('starts on this machine when nothing is known yet', () => {
    const steps = gettingStartedSteps({ check: null, library: null, repos: null, rosterAgents: null, projects: null })
    expect(steps.every((s) => !s.done)).toBe(true)
    expect(nextStep(steps)).toMatchObject({ id: 'machine', href: '#/setup' })
  })

  it('wants a library, then a harness, then a repo', () => {
    expect(nextStep(gettingStartedSteps(input({ library: { exists: false } }))))
      .toMatchObject({ id: 'library', href: '#/setup' })
    const noHarness = check(true, [...MISSING, { code: 'harness_login', message: 'claude is not logged in' }])
    expect(nextStep(gettingStartedSteps(input({ check: noHarness })))).toMatchObject({ id: 'harnesses' })
    expect(nextStep(gettingStartedSteps(input({ repos: [], rosterAgents: null, projects: null }))))
      .toMatchObject({ id: 'repo', href: '#/repos/add' })
  })

  it('sends an uninstalled or uncommitted repo to its Factory tab', () => {
    const fresh = gettingStartedSteps(input({ repos: [repo('n', 'not_installed')], rosterAgents: null, projects: null }))
    expect(nextStep(fresh)).toMatchObject({ id: 'factory', href: '#/r/n/factory', action: 'Nainstalovat factory' })
    const dirty = gettingStartedSteps(input({ repos: [repo('d', 'uncommitted')], rosterAgents: null, projects: null }))
    expect(nextStep(dirty)).toMatchObject({ id: 'factory', action: 'Commitnout konfiguraci' })
    expect(done(input({ repos: [repo('d', 'uncommitted')], rosterAgents: 3 })).roster).toBe(false)
  })

  it('wants the roster checked and a first project in the installed repo', () => {
    expect(nextStep(gettingStartedSteps(input({ rosterAgents: 0 })))).toMatchObject({ id: 'roster', href: '#/r/a/factory' })
    expect(nextStep(gettingStartedSteps(input({ projects: 0 })))).toMatchObject({ id: 'project', href: '#/r/a/backlog/new-container' })
  })

  it('is about the first installed repo', () => {
    expect(focusRepo([repo('gone', 'missing'), repo('new', 'not_installed'), repo('dirty', 'uncommitted'), repo('ok', 'ok')])?.id).toBe('ok')
    expect(focusRepo([repo('gone', 'missing'), repo('new', 'not_installed')])?.id).toBe('new')
    expect(focusRepo([])).toBeNull()
  })
})

describe('detectedHarnesses', () => {
  it('keeps the known harnesses without a missing or login finding', () => {
    expect(detectedHarnesses(check(true, MISSING))).toEqual(['claude'])
    expect(detectedHarnesses(check(true, []))).toEqual(['claude', 'codex', 'pi'])
    expect(detectedHarnesses(null)).toEqual([])
  })
})
