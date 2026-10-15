import { afterEach, describe, expect, it } from 'vitest'
import {
  GRAPH,
  LIBRARY_HREF,
  NEW_CONTAINER,
  NEW_STEP,
  NEW_TASK,
  OVERVIEW_HREF,
  REPOS_ADD_HREF,
  SCREENS,
  SCREEN_LABELS,
  SETUP_HREF,
  currentRepoId,
  graphHref,
  guideHref,
  here,
  repoSettingsHref,
  newContainerHref,
  newStepHref,
  parseRoute,
  repoHref,
  reviewHref,
  runHref,
  taskHref,
  useRepoId,
  usePage,
  useRoute,
  useRouteParams,
} from './router'

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

afterEach(() => {
  go('#/r/haifa/backlog')
})

describe('parseRoute', () => {
  it('parses the overview and the repo pages', () => {
    expect(parseRoute('#/setup')).toMatchObject({ page: 'setup', repo: null, redirect: null })
    expect(parseRoute('#/setup/library')).toMatchObject({ page: 'setup', repo: null, params: ['library'], redirect: null })
    // the library page is the library section of this machine now
    expect(parseRoute('#/library')).toMatchObject({ page: 'setup', repo: null, params: ['library'], redirect: LIBRARY_HREF })
    expect(LIBRARY_HREF).toBe('#/setup/library')
    expect(SETUP_HREF).toBe('#/setup')
    expect(parseRoute('#/overview')).toEqual({ page: 'overview', repo: null, screen: 'backlog', params: [], redirect: null })
    expect(parseRoute('#/repos/add')).toMatchObject({ page: 'repos-add', repo: null, redirect: null })
  })

  it('parses the guide with an optional chapter and section', () => {
    expect(parseRoute('#/guide')).toEqual({ page: 'guide', repo: null, screen: 'backlog', params: [], redirect: null })
    expect(parseRoute('#/guide/instalace')).toMatchObject({ page: 'guide', params: ['instalace'], redirect: null })
    expect(parseRoute('#/guide/backlog/z%C3%A1klady')).toMatchObject({ page: 'guide', params: ['backlog', 'základy'] })
    expect(parseRoute('#/guide/a/b/c')).toMatchObject({ page: 'overview', redirect: OVERVIEW_HREF })
  })

  it('builds guide links', () => {
    expect(guideHref()).toBe('#/guide')
    expect(guideHref('backlog')).toBe('#/guide/backlog')
    expect(guideHref('backlog', 'základy')).toBe('#/guide/backlog/z%C3%A1klady')
  })

  it('sends empty and unknown hashes to the overview', () => {
    for (const hash of ['', '#', '#/', '#/nope', '#/repos/x', '#/repos', '#/r']) {
      expect(parseRoute(hash)).toMatchObject({ page: 'overview', repo: null, redirect: OVERVIEW_HREF })
    }
  })

  it('redirects legacy single-repo routes to the overview', () => {
    for (const hash of ['#/backlog', '#/backlog/T1', '#/runs/r-1/p1', '#/review', '#/settings']) {
      expect(parseRoute(hash)).toMatchObject({ page: 'overview', redirect: '#/overview' })
    }
  })

  it('parses every screen of a repo', () => {
    expect(SCREENS.map((s) => s.id)).toEqual(['backlog', 'runs', 'review', 'factory'])
    for (const screen of ['backlog', 'runs', 'review', 'factory'] as const) {
      expect(parseRoute(`#/r/haifa/${screen}`)).toEqual({ page: 'repo', repo: 'haifa', screen, params: [], redirect: null })
    }
    expect(parseRoute('#/r/x/runs/extra').screen).toBe('runs')
  })

  it('redirects the former settings screen to the settings section of Factory', () => {
    expect(parseRoute('#/r/x/settings')).toEqual({ page: 'repo', repo: 'x', screen: 'factory', params: ['settings'], redirect: '#/r/x/factory/settings' })
    expect(parseRoute('#/r/x/factory/settings')).toEqual({ page: 'repo', repo: 'x', screen: 'factory', params: ['settings'], redirect: null })
    expect(repoSettingsHref('a b')).toBe('#/r/a%20b/factory/settings')
  })

  it('redirects a bare repo and an unknown screen to its backlog', () => {
    expect(parseRoute('#/r/x')).toEqual({ page: 'repo', repo: 'x', screen: 'backlog', params: [], redirect: '#/r/x/backlog' })
    expect(parseRoute('#/r/x/nope/1')).toMatchObject({ page: 'repo', repo: 'x', screen: 'backlog', redirect: '#/r/x/backlog' })
  })

  it('decodes the repo id and the parameters', () => {
    expect(parseRoute('#/r/my%20repo/runs/abc/ph%2F1')).toEqual({
      page: 'repo',
      repo: 'my repo',
      screen: 'runs',
      params: ['abc', 'ph/1'],
      redirect: null,
    })
  })

  it('lists the four screens in order with their labels', () => {
    expect(SCREENS.map((s) => s.label)).toEqual(['Backlog', 'Běhy', 'Review', 'Factory'])
    expect(SCREEN_LABELS.runs).toBe('Běhy')
    expect(SCREEN_LABELS.factory).toBe('Factory')
  })

  it('parses the Factory tab without a redirect', () => {
    expect(parseRoute('#/r/x/factory')).toMatchObject({ page: 'repo', repo: 'x', screen: 'factory', redirect: null })
    expect(repoHref('x', 'factory')).toBe('#/r/x/factory')
  })
})

describe('the current route', () => {
  it('reads the repo of the hash at call time', () => {
    go('#/r/sandbox/runs/r-1')
    expect(currentRepoId()).toBe('sandbox')
    expect(useRepoId().value).toBe('sandbox')
    expect(usePage().value).toBe('repo')
    expect(useRoute().value).toBe('runs')
    expect(useRouteParams().value).toEqual(['r-1'])
    window.location.hash = '#/overview'
    expect(currentRepoId()).toBeNull()
  })

  it('replaces a legacy hash with the overview', () => {
    go('#/runs/r-1')
    expect(window.location.hash).toBe('#/overview')
    expect(usePage().value).toBe('overview')
    expect(useRepoId().value).toBeNull()
  })

  it('replaces a bare repo hash with its backlog', () => {
    go('#/r/sandbox')
    expect(window.location.hash).toBe('#/r/sandbox/backlog')
    expect(usePage().value).toBe('repo')
    expect(useRoute().value).toBe('backlog')
  })
})

describe('hrefs', () => {
  it('carry the current repo', () => {
    expect(here('review')).toBe('#/r/haifa/review')
    expect(runHref('abc')).toBe('#/r/haifa/runs/abc')
    expect(runHref('abc', 'ph/1')).toBe('#/r/haifa/runs/abc/ph%2F1')
    expect(taskHref('M01-S01-T01')).toBe('#/r/haifa/backlog/M01-S01-T01')
    expect(taskHref(NEW_TASK)).toBe('#/r/haifa/backlog/new')
    expect(graphHref('M01-S01')).toBe('#/r/haifa/backlog/graph/M01-S01')
    expect(reviewHref('M01-S01-T01')).toBe('#/r/haifa/review/M01-S01-T01')
    expect(newContainerHref()).toBe('#/r/haifa/backlog/new-container')
    expect(newContainerHref('M01')).toBe('#/r/haifa/backlog/new-container/M01')
    expect(newStepHref()).toBe('#/r/haifa/backlog/new-step')
  })

  it('follow a repo switch', () => {
    go('#/r/other/factory')
    expect(here('runs')).toBe('#/r/other/runs')
    expect(taskHref('T1')).toBe('#/r/other/backlog/T1')
    expect(newStepHref()).toBe('#/r/other/backlog/new-step')
  })

  it('encode the repo id and round-trip through parseRoute', () => {
    go(repoHref('a b/c', 'runs'))
    expect(currentRepoId()).toBe('a b/c')
    expect(runHref('r 1', 'p')).toBe('#/r/a%20b%2Fc/runs/r%201/p')
    expect(parseRoute(runHref('r 1', 'p'))).toMatchObject({ repo: 'a b/c', screen: 'runs', params: ['r 1', 'p'] })
    expect(parseRoute(newContainerHref('M01'))).toMatchObject({ screen: 'backlog', params: [NEW_CONTAINER, 'M01'] })
    expect(parseRoute(newStepHref())).toMatchObject({ screen: 'backlog', params: [NEW_STEP] })
    expect(parseRoute(graphHref('M01'))).toMatchObject({ screen: 'backlog', params: [GRAPH, 'M01'] })
  })

  it('fall back to the overview without a repo', () => {
    go('#/overview')
    expect(here('runs')).toBe(OVERVIEW_HREF)
    expect(taskHref('T1')).toBe(OVERVIEW_HREF)
    expect(runHref('r')).toBe(OVERVIEW_HREF)
    expect(reviewHref('T1')).toBe(OVERVIEW_HREF)
    expect(graphHref('M01')).toBe(OVERVIEW_HREF)
    expect(newContainerHref()).toBe(OVERVIEW_HREF)
    expect(newStepHref()).toBe(OVERVIEW_HREF)
  })

  it('build links to repos and the repo pages', () => {
    expect(repoHref('x')).toBe('#/r/x/backlog')
    expect(repoHref('x', 'review', 'T1')).toBe('#/r/x/review/T1')
    expect(REPOS_ADD_HREF).toBe('#/repos/add')
  })
})
