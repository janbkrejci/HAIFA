import { computed, readonly } from 'vue'
import { createI18n } from 'vue-i18n'
import { cs, en, type MessageKey } from './catalogs'

export type Locale = 'en' | 'cs'
export const LOCALE_STORAGE_KEY = 'haifa.dashboard.locale'

/** Deliberately ignore navigator.language; locale is a browser preference, never repo data. */
export function readStoredLocale(): Locale {
  try {
    return localStorage.getItem(LOCALE_STORAGE_KEY) === 'cs' ? 'cs' : 'en'
  } catch {
    return 'en'
  }
}

export function pluralCategory(count: number, language: Locale = locale.value): Intl.LDMLPluralRule {
  return new Intl.PluralRules(language).select(count)
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: false,
  locale: readStoredLocale(),
  fallbackLocale: 'en',
  flatJson: true,
  messages: { en: { ...en }, cs: { ...cs } },
  pluralRules: {
    en: (count: number) => pluralCategory(count, 'en') === 'one' ? 0 : 1,
    cs: (count: number) => ['one', 'few', 'many', 'other'].indexOf(pluralCategory(count, 'cs')),
  },
})

export const locale = readonly(i18n.global.locale)
export const intlLocale = computed(() => locale.value === 'cs' ? 'cs-CZ' : 'en-US')

/** No reload or component remount: callers keep forms, filters and active work intact. */
export function setLocale(value: unknown): void {
  const next: Locale = value === 'cs' ? 'cs' : 'en'
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, next)
    i18n.global.locale.value = next
  } catch {
    i18n.global.locale.value = 'en'
  }
}

/** Call in a render/computed getter, including derived validation messages. */
export function t(key: MessageKey, params: Record<string, string | number> = {}, count?: number): string {
  // The EN source is mandatory even if CS happens to contain this key.
  if (!i18n.global.te(key, 'en')) throw new Error(`Missing EN translation: ${key}`)
  return i18n.global.t(key, params, count === undefined ? {} : { plural: count })
}

export function useLocale() {
  return { locale, t, setLocale }
}
