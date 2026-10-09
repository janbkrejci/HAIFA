import { describe, expect, it } from 'vitest'
import { highlightValue } from './highlight'

describe('highlightValue', () => {
  it('highlights parsed values and JSON strings, escaping everything', () => {
    expect(highlightValue(null)).toBe('')
    expect(highlightValue({ a: 1 })).toContain('<span class="j-key">&quot;a&quot;</span>')
    expect(highlightValue({ a: 1 })).toContain('<span class="j-num">1</span>')
    expect(highlightValue('{"b":true}')).toContain('<span class="j-bool">true</span>')
    expect(highlightValue('<b>raw</b>')).toBe('&lt;b&gt;raw&lt;/b&gt;')
  })
})
