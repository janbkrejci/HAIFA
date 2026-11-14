import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { computed, defineComponent, nextTick, ref, toRaw } from 'vue'
import { mount } from '@vue/test-utils'
import { i18n, locale, LOCALE_STORAGE_KEY, pluralCategory, readStoredLocale, setLocale, t } from './index'
import { cs, en, validateCatalogs } from './catalogs'
import { fmtClock, fmtCost, fmtDayTime, fmtDuration, fmtInt, fmtMoney4, fmtNumber, fmtTime, fmtTokens } from '../format'

const english = structuredClone(toRaw(i18n.global.getLocaleMessage('en')))
const czech = structuredClone(toRaw(i18n.global.getLocaleMessage('cs')))

beforeEach(() => {
  localStorage.clear()
  setLocale('en')
})
afterEach(() => {
  vi.restoreAllMocks()
  i18n.global.setLocaleMessage('en', english)
  i18n.global.setLocaleMessage('cs', czech)
  setLocale('en')
  localStorage.clear()
})

describe('browser locale preference', () => {
  it('boots in EN in a Czech browser and reloads an explicit CS preference', async () => {
    localStorage.clear()
    vi.spyOn(navigator, 'language', 'get').mockReturnValue('cs-CZ')
    vi.spyOn(navigator, 'languages', 'get').mockReturnValue(['cs-CZ', 'cs'])
    vi.resetModules()
    const boot = await import('./index')
    expect(boot.locale.value).toBe('en')
    boot.setLocale('cs')
    window.location.hash = '#/r/another-repo/backlog'
    expect(boot.locale.value).toBe('cs')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('cs')
    vi.resetModules()
    expect((await import('./index')).locale.value).toBe('cs')
  })

  it.each(['de', 'CS', '', 'null'])('falls back to EN for stored %s', (value) => {
    localStorage.setItem(LOCALE_STORAGE_KEY, value)
    expect(readStoredLocale()).toBe('en')
    setLocale(value)
    expect(locale.value).toBe('en')
  })

  it('falls back to EN if storage cannot be accessed or read', () => {
    vi.spyOn(window, 'localStorage', 'get').mockImplementation(() => { throw new Error('blocked') })
    expect(readStoredLocale()).toBe('en')
    setLocale('cs')
    expect(locale.value).toBe('en')
  })

  it('falls back to EN if reading storage throws', () => {
    vi.spyOn(localStorage, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    expect(readStoredLocale()).toBe('en')
  })

  it('falls back to EN if storage writes fail, including after CS was selected', () => {
    setLocale('cs')
    vi.spyOn(localStorage, 'setItem').mockImplementation(() => { throw new Error('quota') })
    setLocale('cs')
    expect(locale.value).toBe('en')
  })
})

describe('catalogs', () => {
  it('has complete catalogs with compatible placeholders and plural forms', () => {
    expect(validateCatalogs(en, cs)).toEqual([])
    expect(validateCatalogs({ key: '{field}' }, {})).toContain('Missing CS key: key')
    expect(validateCatalogs({}, { key: 'Text' })).toContain('Missing EN key: key')
    expect(validateCatalogs({ key: '{field}' }, { key: '{name}' })).toContain('Incompatible CS placeholders: key')
    expect(validateCatalogs({ key: '{n} item | {n} items' }, { key: '{n} položka | položky | {n} položky | {n} položek' }))
      .toContain('Incompatible CS placeholders: key')
    expect(validateCatalogs({ key: 'one | other' }, { key: 'jedna | jiné' })).toContain('Invalid CS plurals: key')
  })

  it('falls back to EN for a missing CS entry, but refuses a missing EN source', () => {
    // Bypass static completeness here to exercise a missing catalog at runtime.
    i18n.global.setLocaleMessage('cs', {} as typeof cs)
    setLocale('cs')
    expect(t('validation.required', { field: 'Name' })).toBe('Name is required.')
    i18n.global.setLocaleMessage('cs', czech)
    i18n.global.setLocaleMessage('en', {} as typeof en)
    expect(() => t('common.save')).toThrow('Missing EN translation: common.save')
  })

  it.each([
    [0, 'other', 'other', '0 items', '0 položek'],
    [1, 'one', 'one', '1 item', '1 položka'],
    [2, 'other', 'few', '2 items', '2 položky'],
    [5, 'other', 'other', '5 items', '5 položek'],
    [1.5, 'other', 'many', '1.5 items', '1,5 položky'],
  ])('uses Intl plurals for %s', (count, enCategory, csCategory, enText, csText) => {
    expect(pluralCategory(count as number)).toBe(enCategory)
    expect(t('counts.items', { count: fmtNumber(count as number) }, count as number)).toBe(enText)
    setLocale('cs')
    expect(pluralCategory(count as number)).toBe(csCategory)
    expect(t('counts.items', { count: fmtNumber(count as number) }, count as number)).toBe(csText)
  })
})

describe('reactivity and localized formatting', () => {
  it('updates derived labels, validation and formatters without remounting or losing work', async () => {
    let mounts = 0
    const Screen = defineComponent({
      setup() {
        mounts++
        const draft = ref('unfinished')
        const filter = ref('running')
        const label = computed(() => t('common.save'))
        const validation = computed(() => t('validation.required', { field: 'Name' }))
        const number = computed(() => fmtNumber(1234.5))
        return { draft, filter, label, validation, number }
      },
      template: '<div><input v-model="draft" data-test="draft"><select v-model="filter"><option>running</option><option>done</option></select><button data-test="save">{{ label }}</button><p>{{ validation }}</p><output>{{ number }}</output></div>',
    })
    const screen = mount(Screen)
    await screen.get('input').setValue('my work')
    await screen.get('select').setValue('done')
    expect(screen.text()).toContain('Name is required.')
    expect(screen.get('output').text()).toBe('1,234.5')
    setLocale('cs')
    await nextTick()
    expect(screen.get('[data-test="save"]').text()).toBe('Uložit')
    expect(screen.text()).toContain('Pole Name je povinné.')
    expect(screen.get('output').text()).toBe(new Intl.NumberFormat('cs-CZ').format(1234.5))
    expect((screen.get('input').element as HTMLInputElement).value).toBe('my work')
    expect((screen.get('select').element as HTMLSelectElement).value).toBe('done')
    expect(mounts).toBe(1)
    screen.unmount()
  })

  it.each(['en', 'cs'] as const)('formats numbers and USD with %s conventions', (language) => {
    setLocale(language)
    const tag = language === 'en' ? 'en-US' : 'cs-CZ'
    for (const n of [0, 1, 2, 5, 1.5, 1234.5]) {
      expect(fmtInt(n)).toBe(new Intl.NumberFormat(tag).format(n))
      const digits = n >= 1 ? 2 : 4
      expect(fmtCost(n)).toBe(new Intl.NumberFormat(tag, { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits }).format(n))
      expect(fmtMoney4(n)).toBe(new Intl.NumberFormat(tag, { style: 'currency', currency: 'USD', minimumFractionDigits: 4, maximumFractionDigits: 4 }).format(n))
    }
    if (language === 'cs') {
      expect(fmtDuration(1.5)).toBe('1,5s')
      expect(fmtTokens(1500)).toBe('1,5k')
    }
  })

  it('recomputes local dates and clocks while keeping the browser time zone and instant', () => {
    const iso = '2026-10-04T12:34:56+03:00'
    const date = new Date(iso)
    const formatted = computed(() => [fmtTime(iso), fmtClock(iso), fmtDayTime(iso)])
    for (const language of ['en', 'cs'] as const) {
      setLocale(language)
      const tag = language === 'en' ? 'en-US' : 'cs-CZ'
      expect(formatted.value).toEqual([
        date.toLocaleString(tag, { hour12: false }),
        date.toLocaleTimeString(tag, { hour12: false }),
        date.toLocaleString(tag, { day: 'numeric', month: 'numeric', hour: '2-digit', minute: '2-digit' }),
      ])
    }
    expect(date.toISOString()).toBe('2026-10-04T09:34:56.000Z')
  })
})
