import { describe, expect, it } from 'vitest'
import { chainStateLabel, chainsOf, skipReasonLabel, type Chain } from './chains'

describe('skipReasonLabel', () => {
  it('names every reason of the chain in Czech', () => {
    expect(skipReasonLabel('writes_overlap')).toBe('překryv writes')
    expect(skipReasonLabel('exclusive')).toBe('jen samostatně')
    expect(skipReasonLabel('waits_on_pr')).toBe('čeká na PR')
    expect(skipReasonLabel('blocked')).toBe('blokováno')
    expect(skipReasonLabel('no_workflow')).toBe('bez workflow')
    expect(skipReasonLabel('in_review')).toBe('v review')
    expect(skipReasonLabel('running')).toBe('běží')
    expect(skipReasonLabel('cannot_start')).toBe('nelze spustit')
    expect(skipReasonLabel('excluded')).toBe('odloženo v kanbanu')
    expect(skipReasonLabel('something_new')).toBe('something_new')
  })
})

describe('chains', () => {
  const base = { state: 'finished', stop: 'exhausted' } as Chain

  it('labels the state', () => {
    expect(chainStateLabel({ ...base, state: 'running' })).toBe('běží')
    expect(chainStateLabel(base)).toBe('skončil: není co spustit')
    expect(chainStateLabel({ ...base, stop: 'failed' })).toBe('skončil: běh selhal')
    expect(chainStateLabel({ ...base, state: 'aborted' })).toBe('přerušen')
  })

  it('reads chains from any reply', () => {
    expect(chainsOf(null)).toEqual([])
    expect(chainsOf({ runs: [] })).toEqual([])
    expect(chainsOf({ chains: [base] })).toEqual([base])
  })
})
