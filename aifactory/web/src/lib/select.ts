// Shared types and pure logic for the dashboard dropdown (components/ui/SelectMenu.vue).

export interface SelectOption {
  value: string
  label: string
}

function fold(text: string): string {
  return text.toLocaleLowerCase('cs')
}

/**
 * Typeahead: index of the first label starting with `query` (case-insensitive),
 * searching from `from + 1` and wrapping around. Returns -1 when nothing matches.
 */
export function typeaheadIndex(labels: string[], query: string, from: number): number {
  const n = labels.length
  if (!n || !query) return -1
  const q = fold(query)
  for (let step = 1; step <= n; step++) {
    const i = (((from + step) % n) + n) % n
    if (fold(labels[i] ?? '').startsWith(q)) return i
  }
  return -1
}

/** A buffer of one repeated character ("tt") cycles through items with that first letter. */
export function typeaheadQuery(buffer: string): string {
  const first = buffer.charAt(0)
  return buffer.length > 1 && [...buffer].every((c) => fold(c) === fold(first)) ? first : buffer
}
