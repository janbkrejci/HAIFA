/** Stable UI keys only. IDs, routes, API codes and user content never belong here. */
export const en = {
  'common.save': 'Save',
  'common.cancel': 'Cancel',
  'validation.required': '{field} is required.',
  'counts.items': '{count} item | {count} items',
  'time.justNow': 'just now',
}

export const cs: Record<keyof typeof en, string> = {
  'common.save': 'Uložit',
  'common.cancel': 'Zrušit',
  'validation.required': 'Pole {field} je povinné.',
  // Intl categories: one, few, many (fractional), other.
  'counts.items': '{count} položka | {count} položky | {count} položky | {count} položek',
  'time.justNow': 'právě teď',
}

export type MessageKey = keyof typeof en
export type Catalog = Record<string, string>

/** CI checks completeness; runtime may still fall back from a missing CS entry to EN. */
export function validateCatalogs(english: Catalog, czech: Catalog): string[] {
  const errors: string[] = []
  const placeholders = (text: string) => [...new Set(
    [...text.matchAll(/\{(\w+)\}/g)].map((match) => match[1]),
  )].sort().join(',')
  for (const key of new Set([...Object.keys(english), ...Object.keys(czech)])) {
    if (!Object.hasOwn(english, key)) errors.push(`Missing EN key: ${key}`)
    if (!Object.hasOwn(czech, key)) errors.push(`Missing CS key: ${key}`)
    const source = english[key]
    if (source === undefined) continue
    const expected = placeholders(source.split('|')[0]!)
    for (const [language, catalog, forms] of [['EN', english, 2], ['CS', czech, 4]] as const) {
      const message = catalog[key]
      if (message === undefined) continue
      const branches = message.split('|')
      if (!message.trim()) errors.push(`Empty ${language} message: ${key}`)
      if (branches.length > 1 && branches.length !== forms) errors.push(`Invalid ${language} plurals: ${key}`)
      if ((source.includes('|')) !== message.includes('|')) errors.push(`Incompatible ${language} plurals: ${key}`)
      if (branches.some((branch) => placeholders(branch) !== expected)) {
        errors.push(`Incompatible ${language} placeholders: ${key}`)
      }
    }
  }
  return errors
}
