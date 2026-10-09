import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  LIVE_DEBOUNCE_MS,
  onLive,
  resetLiveForTests,
  touchesContainer,
  touchesTask,
  touchesWorkflows,
} from './live'
import { FakeEventSource, filesEvent, traceEvent } from '@/test/fakeEventSource'

beforeEach(() => {
  vi.useFakeTimers()
  FakeEventSource.reset()
  vi.stubGlobal('EventSource', FakeEventSource)
})

let visibility: DocumentVisibilityState = 'visible'

function setVisibility(state: DocumentVisibilityState) {
  visibility = state
  document.dispatchEvent(new Event('visibilitychange'))
}

beforeEach(() => {
  visibility = 'visible'
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => visibility })
})

afterEach(() => {
  resetLiveForTests()
  vi.unstubAllGlobals()
  vi.useRealTimers()
  delete (document as unknown as Record<string, unknown>).visibilityState
})

describe('path helpers', () => {
  it('matches the file of a task', () => {
    const paths = ['backlog/M01-core/S01-model/M01-S01-T01-schema.md']
    expect(touchesTask(paths, 'M01-S01-T01')).toBe(true)
    expect(touchesTask(paths, 'M01-S01-T02')).toBe(false)
    expect(touchesTask(['backlog/M01-S01-T1.md'], 'M01-S01-T1')).toBe(true)
    expect(touchesTask(paths, 'M01-S01-T0')).toBe(false)
  })

  it('matches a module or step', () => {
    const paths = ['backlog/M01-core/S01-model/M01-S01-T01-schema.md']
    expect(touchesContainer(paths, 'M01')).toBe(true)
    expect(touchesContainer(paths, 'M01-S01')).toBe(true)
    expect(touchesContainer(paths, 'M02')).toBe(false)
  })

  it('matches workflows and the shared config', () => {
    expect(touchesWorkflows(['.factory/workflows/plan.yaml'])).toBe(true)
    expect(touchesWorkflows(['.factory/config.yaml'])).toBe(true)
    expect(touchesWorkflows(['.factory/agents.yaml'])).toBe(false)
  })
})

describe('onLive', () => {
  it('shares one EventSource and closes it with the last subscriber', () => {
    const offA = onLive({})
    const offB = onLive({})
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.latest().url).toBe('/api/repos/haifa/live')
    offA()
    expect(FakeEventSource.latest().closed).toBe(false)
    offB()
    expect(FakeEventSource.latest().closed).toBe(true)
  })

  it('merges events within the debounce window', () => {
    const files = vi.fn()
    const trace = vi.fn()
    onLive({ files, trace })
    const source = FakeEventSource.latest()
    source.emit('hello', { interval: 0.5 })
    source.emit('files', filesEvent(['backlog/a.md'], ['backlog'], 1))
    source.emit('files', filesEvent(['.factory/config.yaml'], ['factory'], 2))
    source.emit('trace', traceEvent({ run_ids: ['r-1'], task_ids: ['T1'] }))
    expect(files).not.toHaveBeenCalled()
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(files).toHaveBeenCalledTimes(1)
    expect(files.mock.calls[0][0]).toEqual({
      seq: 2,
      areas: ['backlog', 'factory'],
      paths: ['.factory/config.yaml', 'backlog/a.md'],
      truncated: false,
    })
    expect(trace).toHaveBeenCalledTimes(1)
    expect(trace.mock.calls[0][0].run_ids).toEqual(['r-1'])
  })

  it('asks for a resync after a reconnect', () => {
    const resync = vi.fn()
    const files = vi.fn()
    onLive({ resync, files })
    const source = FakeEventSource.latest()
    source.emit('hello')
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(resync).not.toHaveBeenCalled()
    source.emit('hello')
    source.emit('files', filesEvent(['backlog/a.md']))
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(resync).toHaveBeenCalledTimes(1)
    expect(files).not.toHaveBeenCalled()
    source.emit('resync', { seq: 9 })
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(resync).toHaveBeenCalledTimes(2)
  })

  it('does nothing after unsubscribing', () => {
    const files = vi.fn()
    const off = onLive({ files })
    FakeEventSource.latest().emit('files', filesEvent(['backlog/a.md']))
    off()
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(files).not.toHaveBeenCalled()
  })

  it('is a no-op without EventSource', () => {
    vi.unstubAllGlobals()
    vi.stubGlobal('EventSource', undefined)
    const off = onLive({})
    expect(FakeEventSource.instances).toHaveLength(0)
    off()
  })

  it('opens nothing without a repo in the URL', () => {
    window.location.hash = '#/overview'
    const off = onLive({})
    expect(FakeEventSource.instances).toHaveLength(0)
    off()
  })
})

describe('repo switch', () => {
  it('opens a new source when the screen remounts on another repo', () => {
    const off = onLive({})
    const first = FakeEventSource.latest()
    off()
    expect(first.closed).toBe(true)
    window.location.hash = '#/r/other/backlog'
    onLive({})
    expect(FakeEventSource.latest().url).toBe('/api/repos/other/live')
  })

  it('never keeps a source of another repo', () => {
    onLive({})
    const first = FakeEventSource.latest()
    window.location.hash = '#/r/other/backlog'
    onLive({})
    expect(first.closed).toBe(true)
    expect(FakeEventSource.latest().url).toBe('/api/repos/other/live')
    expect(FakeEventSource.instances.filter((s) => !s.closed)).toHaveLength(1)
  })
})

describe('tab visibility', () => {
  it('closes in a hidden tab and reopens with a resync when visible again', () => {
    const resync = vi.fn()
    onLive({ resync })
    const first = FakeEventSource.latest()
    setVisibility('hidden')
    expect(first.closed).toBe(true)
    setVisibility('visible')
    expect(FakeEventSource.instances).toHaveLength(2)
    const second = FakeEventSource.latest()
    expect(second.closed).toBe(false)
    expect(second.url).toBe('/api/repos/haifa/live')
    vi.advanceTimersByTime(LIVE_DEBOUNCE_MS)
    expect(resync).toHaveBeenCalledTimes(1)
  })

  it('opens nothing while hidden and nothing for no subscribers', () => {
    setVisibility('hidden')
    const off = onLive({})
    expect(FakeEventSource.instances).toHaveLength(0)
    off()
    setVisibility('visible')
    expect(FakeEventSource.instances).toHaveLength(0)
  })
})
