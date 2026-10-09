// Formatting, ported from the sssf visualizer's src/lib/format.ts.
// Durations here are in SECONDS (the API's duration_s), not milliseconds.

export function fmtDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  if (seconds < 1) return `${seconds.toFixed(2)}s`
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const m = Math.floor(seconds / 60)
  const rem = Math.round(seconds % 60)
  if (m < 60) return `${m}m ${String(rem).padStart(2, '0')}s`
  const h = Math.floor(m / 60)
  return `${h}h ${String(m % 60).padStart(2, '0')}m`
}

export function fmtTokens(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}k`
  return `${(n / 1_000_000).toFixed(2)}M`
}

export function fmtCost(n: number | null | undefined): string {
  if (n == null) return '—'
  return n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4)}`
}

/** Local date and time, or — for a missing or invalid timestamp. */
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return '—'
  return new Date(t).toLocaleString('cs-CZ', { hour12: false })
}

/** Day, month and time without the year ("4. 10. 12:00"), or null for a missing or invalid timestamp. */
export function fmtDayTime(iso: string | null | undefined): string | null {
  if (!iso) return null
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return null
  return at.toLocaleString('cs-CZ', { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** Local time of day only, or — for a missing or invalid timestamp. */
export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (!Number.isFinite(t)) return '—'
  return new Date(t).toLocaleTimeString('cs-CZ', { hour12: false })
}

/** Dollars to four places: per-component costs run to fractions of a cent. */
export function fmtMoney4(n: number | null | undefined): string {
  return `$${(n ?? 0).toFixed(4)}`
}

const INT = new Intl.NumberFormat('cs-CZ')

/** A whole count with Czech thousands separators. */
export function fmtInt(n: number | null | undefined): string {
  return INT.format(n ?? 0)
}

/** Czech plural: 1 → one, 2–4 → few, otherwise many. */
export function plural(n: number, one: string, few: string, many: string): string {
  if (n === 1) return one
  if (n >= 2 && n <= 4) return few
  return many
}

/** Seconds from start to end, or null when either is missing or invalid. */
export function secondsBetween(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
): number | null {
  if (!startIso || !endIso) return null
  const a = new Date(startIso).getTime()
  const b = new Date(endIso).getTime()
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null
  return (b - a) / 1000
}

/** Epoch ms of a timestamp, NaN for a missing or invalid one. */
export function ts(iso: string | null | undefined): number {
  if (!iso) return NaN
  return new Date(iso).getTime()
}

/** Compact offset label for time axes: 0s, 30s, 1m, 1m30s, 2m, 1h05m. */
export function fmtOffset(ms: number): string {
  const s = Math.round(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) {
    const rem = s % 60
    return rem ? `${m}m${String(rem).padStart(2, '0')}s` : `${m}m`
  }
  const h = Math.floor(m / 60)
  const mrem = m % 60
  return mrem ? `${h}h${String(mrem).padStart(2, '0')}m` : `${h}h`
}

const TICK_STEPS_MS = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600].map((s) => s * 1000)

/** Evenly-stepped time-axis ticks over a span, ≤ maxTicks of them. */
export function axisTicks(spanMs: number, maxTicks = 8): { pct: number; label: string }[] {
  const span = Math.max(spanMs, 1)
  // Past the largest step, whole hours keep the count within maxTicks.
  const step =
    TICK_STEPS_MS.find((s) => span / s <= maxTicks) ?? Math.ceil(span / maxTicks / 3_600_000) * 3_600_000
  const out: { pct: number; label: string }[] = []
  for (let t = 0; t <= span; t += step) {
    out.push({ pct: (t / span) * 100, label: fmtOffset(t) })
  }
  return out
}

/** A whole-second span: 45s, 3m 05s, 1h 02m, 2d 03h; — for a missing or negative one. */
export function fmtElapsed(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return '—'
  const s = Math.floor(seconds)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ${String(s % 60).padStart(2, '0')}s`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ${String(m % 60).padStart(2, '0')}m`
  return `${Math.floor(h / 24)}d ${String(h % 24).padStart(2, '0')}h`
}

/** How long ago: "právě teď", "před 5 min", "před 3 h", "před 2 d"; — for a missing age. */
export function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—'
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return 'právě teď'
  const m = Math.floor(s / 60)
  if (m < 60) return `před ${m} min`
  const h = Math.floor(m / 60)
  if (h < 24) return `před ${h} h`
  return `před ${Math.floor(h / 24)} d`
}

/** The short form of a commit sha (first `n` characters); '' for a missing one. */
export function shortSha(sha: string | null | undefined, n = 7): string {
  return sha ? sha.slice(0, n) : ''
}

/** The message of a caught error: Error.message, anything else as text. */
export function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}
