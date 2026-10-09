import { describe, expect, it } from 'vitest'
import { typeaheadIndex, typeaheadQuery } from './select'

const labels = ['vše', 'Todo', 'běží', 'blokováno', 'Čeká', 'cancelled']

describe('typeaheadIndex', () => {
  it('matches the start of a label case-insensitively', () => {
    expect(typeaheadIndex(labels, 't', -1)).toBe(1)
    expect(typeaheadIndex(labels, 'TO', -1)).toBe(1)
  })

  it('folds diacritics case, not the accents', () => {
    expect(typeaheadIndex(labels, 'č', -1)).toBe(4)
    expect(typeaheadIndex(labels, 'c', -1)).toBe(5)
  })

  it('searches after `from` and wraps around', () => {
    expect(typeaheadIndex(labels, 'b', 2)).toBe(3)
    expect(typeaheadIndex(labels, 'b', 3)).toBe(2)
    expect(typeaheadIndex(labels, 'v', 4)).toBe(0)
  })

  it('stays on the current item when it is the only match', () => {
    expect(typeaheadIndex(labels, 'v', 0)).toBe(0)
  })

  it('returns -1 when nothing matches', () => {
    expect(typeaheadIndex(labels, 'x', 0)).toBe(-1)
    expect(typeaheadIndex([], 'a', 0)).toBe(-1)
    expect(typeaheadIndex(labels, '', 0)).toBe(-1)
  })
})

describe('typeaheadQuery', () => {
  it('collapses one repeated character', () => {
    expect(typeaheadQuery('bb')).toBe('b')
    expect(typeaheadQuery('bB')).toBe('b')
    expect(typeaheadQuery('bl')).toBe('bl')
    expect(typeaheadQuery('b')).toBe('b')
  })
})
