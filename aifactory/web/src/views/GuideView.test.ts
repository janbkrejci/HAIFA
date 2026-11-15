import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import GuideView from './GuideView.vue'

const CHAPTERS = [
  { id: 'uvod', title: 'Úvod', markdown: '# Úvod\n\nCo je HAIFA.\n\n## Pojmy\n\nTask a běh.\n' },
  { id: 'backlog', title: 'Backlog', markdown: '# Backlog\n\n## Spuštění běhu\n\nTlačítko **Spustit**.\n\n| Kód | Oprava |\n| --- | --- |\n| `a` | b |\n' },
]

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function api(ok = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (url !== '/api/guide') throw new Error(`unexpected ${url}`)
    return ok
      ? new Response(JSON.stringify({ ok: true, data: { chapters: CHAPTERS }, error: null, warnings: [] }))
      : new Response(JSON.stringify({ ok: false, data: null, error: { code: 'boom', message: 'nejde to' }, warnings: [] }), { status: 500 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => setLocale('cs'))
afterEach(() => setLocale('en'))
enableAutoUnmount(afterEach)
afterEach(() => { vi.unstubAllGlobals(); go('#/overview') })
Element.prototype.scrollIntoView ??= () => {}

describe('GuideView', () => {
  it('opens the first chapter and lists every chapter', async () => {
    go('#/guide')
    api()
    const wrapper = mount(GuideView); await flushPromises()
    expect(wrapper.get('[data-test="guide-article"]').html()).toContain('<h1>Úvod</h1>')
    expect(wrapper.get('[data-test="guide-chapter-uvod"]').classes()).toContain('active')
    expect(wrapper.get('[data-test="guide-chapter-backlog"]').attributes('href')).toBe('#/guide/backlog')
    expect(wrapper.get('[data-test="guide-next"]').attributes('href')).toBe('#/guide/backlog')
    expect(wrapper.find('[data-test="guide-previous"]').exists()).toBe(false)
  })

  it('renders the chapter of the URL with section ids and tables', async () => {
    go('#/guide/backlog/spusteni-behu')
    api()
    const wrapper = mount(GuideView); await flushPromises()
    const article = wrapper.get('[data-test="guide-article"]')
    expect(article.get('h2').attributes('id')).toBe('spusteni-behu')
    expect(article.find('table.md-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('Spuštění běhu')
    expect(wrapper.get('[data-test="guide-previous"]').attributes('href')).toBe('#/guide/uvod')
  })

  it('searches all chapters', async () => {
    go('#/guide')
    api()
    const wrapper = mount(GuideView); await flushPromises()
    await wrapper.get('[data-test="guide-search"]').setValue('tlacitko')
    const hits = wrapper.findAll('[data-test="guide-hit"]')
    expect(hits.map((h) => h.attributes('href'))).toEqual(['#/guide/backlog/spusteni-behu'])
    await wrapper.get('[data-test="guide-search"]').setValue('nic takoveho')
    expect(wrapper.get('[data-test="guide-hits"]').text()).toContain('Nic nenalezeno')
  })

  it('shows a failed load', async () => {
    go('#/guide')
    api(false)
    const wrapper = mount(GuideView); await flushPromises()
    expect(wrapper.get('[data-test="guide-error"]').text()).toContain('nejde to')
  })
})


it('translates guide controls and keeps the query, chapter and Czech document intact', async () => {
  go('#/guide/backlog')
  const fetchMock = api()
  const wrapper = mount(GuideView)
  await flushPromises()
  const article = wrapper.get('[data-test="guide-article"]').element
  await wrapper.get('[data-test="guide-search"]').setValue('missing')
  for (const [language, heading, search, empty] of [
    ['en', 'Guide', 'Search the guide', 'Nothing found.'],
    ['cs', 'Příručka', 'Hledat v příručce', 'Nic nenalezeno.'],
  ] as const) {
    setLocale(language)
    await flushPromises()
    expect(wrapper.get('h1').text()).toBe(heading)
    expect(wrapper.get('input').attributes('aria-label')).toBe(search)
    expect(wrapper.get('[data-test="guide-hits"]').text()).toBe(empty)
    expect(wrapper.get('input').element).toHaveProperty('value', 'missing')
    expect(wrapper.get('[data-test="guide-article"]').element).toBe(article)
    expect(wrapper.get('article').attributes('lang')).toBe('cs')
  }
  expect(fetchMock).toHaveBeenCalledTimes(1)
})

it('retranslates a failed guide request without fetching again', async () => {
  const fetchMock = api(false)
  const wrapper = mount(GuideView)
  await flushPromises()
  for (const [language, message] of [['en', 'Could not load the guide: nejde to'], ['cs', 'Příručku se nepodařilo načíst: nejde to']] as const) {
    setLocale(language)
    await flushPromises()
    expect(wrapper.get('[data-test="guide-error"]').text()).toBe(message)
  }
  expect(fetchMock).toHaveBeenCalledTimes(1)
})
