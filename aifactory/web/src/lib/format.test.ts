import { describe, expect, it } from 'vitest'
import {
  axisTicks,
  fmtOffset,
  ts,
  fmtClock,
  fmtCost,
  fmtDuration,
  fmtInt,
  fmtMoney4,
  fmtTime,
  fmtTokens,
  plural,
  errorText,
  fmtDayTime,
  shortSha,
  secondsBetween,
} from './format'

describe('format', () => {
  it('formats durations in seconds', () => {
    expect(fmtDuration(null)).toBe('—')
    expect(fmtDuration(-1)).toBe('—')
    expect(fmtDuration(0.5)).toBe('0.50s')
    expect(fmtDuration(12.34)).toBe('12.3s')
    expect(fmtDuration(300)).toBe('5m 00s')
    expect(fmtDuration(3725)).toBe('1h 02m')
  })

  it('formats tokens', () => {
    expect(fmtTokens(null)).toBe('—')
    expect(fmtTokens(999)).toBe('999')
    expect(fmtTokens(1180)).toBe('1.2k')
    expect(fmtTokens(1_234_567)).toBe('1.23M')
  })

  it('formats cost', () => {
    expect(fmtCost(undefined)).toBe('—')
    expect(fmtCost(0.25)).toBe('$0.2500')
    expect(fmtCost(12.345)).toBe('$12.35')
  })

  it('formats times', () => {
    expect(fmtTime(null)).toBe('—')
    expect(fmtTime('nope')).toBe('—')
    expect(fmtTime('2026-01-01T10:00:00+00:00')).toMatch(/2026/)
  })

  it('formats day and time without the year', () => {
    expect(fmtDayTime(null)).toBeNull()
    expect(fmtDayTime('nope')).toBeNull()
    const text = fmtDayTime('2026-10-04T12:00:00+00:00')
    expect(text).toMatch(/\d{1,2}:\d{2}/)
    expect(text).not.toMatch(/2026/)
  })

  it('shortens a commit sha', () => {
    expect(shortSha('0123456789abcdef')).toBe('0123456')
    expect(shortSha('0123456789abcdef', 8)).toBe('01234567')
    expect(shortSha('abc')).toBe('abc')
    expect(shortSha(null)).toBe('')
    expect(shortSha(undefined)).toBe('')
  })

  it('reads the message of a caught error', () => {
    expect(errorText(new Error('boom'))).toBe('boom')
    expect(errorText('plain')).toBe('plain')
    expect(errorText(42)).toBe('42')
  })

  it('formats clock times', () => {
    expect(fmtClock(null)).toBe('—')
    expect(fmtClock('nope')).toBe('—')
    expect(fmtClock('2026-01-01T10:00:00+00:00')).toMatch(/^\d{1,2}:\d{2}:\d{2}$/)
  })

  it('formats money to four places', () => {
    expect(fmtMoney4(0)).toBe('$0.0000')
    expect(fmtMoney4(null)).toBe('$0.0000')
    expect(fmtMoney4(0.1)).toBe('$0.1000')
    expect(fmtMoney4(1.23456)).toBe('$1.2346')
  })

  it('formats integers', () => {
    expect(fmtInt(999)).toBe('999')
    expect(fmtInt(null)).toBe('0')
    expect(fmtInt(12345).replace(/\s/g, ' ')).toBe('12 345')
  })

  it('picks the Czech plural', () => {
    expect(plural(1, 'řádek', 'řádky', 'řádků')).toBe('řádek')
    expect(plural(3, 'řádek', 'řádky', 'řádků')).toBe('řádky')
    expect(plural(12, 'řádek', 'řádky', 'řádků')).toBe('řádků')
    expect(plural(0, 'řádek', 'řádky', 'řádků')).toBe('řádků')
  })

  it('measures seconds between two timestamps', () => {
    expect(secondsBetween('2026-01-01T10:00:00Z', '2026-01-01T10:01:30Z')).toBe(90)
    expect(secondsBetween(null, '2026-01-01T10:01:30Z')).toBeNull()
    expect(secondsBetween('2026-01-01T10:00:00Z', 'bad')).toBeNull()
  })
})

describe('time axis helpers', () => {
  it('parses timestamps to epoch ms', () => {
    expect(ts(null)).toBeNaN()
    expect(ts('bad')).toBeNaN()
    expect(ts('2026-01-01T00:00:01Z')).toBe(Date.UTC(2026, 0, 1, 0, 0, 1))
  })

  it('formats axis offsets', () => {
    expect(fmtOffset(45_000)).toBe('45s')
    expect(fmtOffset(120_000)).toBe('2m')
    expect(fmtOffset(125_000)).toBe('2m05s')
    expect(fmtOffset(3_600_000)).toBe('1h')
    expect(fmtOffset(3_900_000)).toBe('1h05m')
  })

  it('steps axis ticks within the span', () => {
    const ticks = axisTicks(60_000, 7)
    expect(ticks[0]).toEqual({ pct: 0, label: '0s' })
    expect(ticks.length).toBeLessThanOrEqual(7)
    expect(ticks.at(-1)!.pct).toBeLessThanOrEqual(100)
    expect(axisTicks(30 * 24 * 3_600_000, 7).length).toBeLessThanOrEqual(7)
  })
})
