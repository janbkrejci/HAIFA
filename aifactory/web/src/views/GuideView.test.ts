import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { setLocale } from '@/lib/i18n'
import { deferred } from '@/test/deferred'
import GuideView from './GuideView.vue'

const CHAPTERS = [
  { id: 'uvod', title: 'Úvod', markdown: '# Úvod\n\nCo je GIRO.\n\n## Pojmy\n\nTask a běh.\n' },
  { id: 'backlog', title: 'Backlog', markdown: '# Backlog\n\n## Spuštění běhu\n\nTlačítko **Spustit**.\n\n| Kód | Oprava |\n| --- | --- |\n| `a` | b |\n' },
]
const EN_CHAPTERS = [
  { id: 'uvod', title: 'Introduction', markdown: '# Introduction\n\nWhat is GIRO.\n\n## Terms <!-- section:pojmy -->\n\nTask and run.\n' },
  { id: 'backlog', title: 'Backlog', markdown: '# Backlog\n\n## Starting a run <!-- section:spusteni-behu -->\n\nThe **Run** button.\n' },
]

function response(chapters = CHAPTERS) {
  return new Response(JSON.stringify({ ok: true, data: { chapters }, error: null, warnings: [] }))
}

function go(hash: string) {
  window.location.hash = hash
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

function api(ok = true) {
  const fetchMock = vi.fn(async (url: string) => {
    if (!['/api/guide?locale=en', '/api/guide?locale=cs'].includes(url)) throw new Error(`unexpected ${url}`)
    return ok
      ? response(url.endsWith('=en') ? EN_CHAPTERS : CHAPTERS)
      : new Response(JSON.stringify({ ok: false, data: null, error: { code: 'boom', message: 'nejde to' }, warnings: [] }), { status: 500 })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const mounted: { unmount(): void }[] = []
function mountGuide() {
  const wrapper = mount(GuideView)
  mounted.push(wrapper)
  return wrapper
}

beforeEach(() => { setLocale('cs') })
afterEach(() => {
  mounted.splice(0).forEach((wrapper) => wrapper.unmount())
  setLocale('en')
  vi.unstubAllGlobals()
  go('#/overview')
  localStorage.clear()
})
Element.prototype.scrollIntoView ??= () => {}

describe('GuideView', () => {
  it('opens the first chapter and lists every chapter', async () => {
    go('#/guide')
    api()
    const wrapper = mountGuide(); await flushPromises()
    expect(wrapper.get('[data-test="guide-article"]').html()).toContain('<h1>Úvod</h1>')
    expect(wrapper.get('[data-test="guide-chapter-uvod"]').classes()).toContain('active')
    expect(wrapper.get('[data-test="guide-chapter-backlog"]').attributes('href')).toBe('#/guide/backlog')
    expect(wrapper.get('[data-test="guide-next"]').attributes('href')).toBe('#/guide/backlog')
    expect(wrapper.find('[data-test="guide-previous"]').exists()).toBe(false)
  })

  it('renders the chapter of the URL with section ids and tables', async () => {
    go('#/guide/backlog/spusteni-behu')
    api()
    const wrapper = mountGuide(); await flushPromises()
    const article = wrapper.get('[data-test="guide-article"]')
    expect(article.get('h2').attributes('id')).toBe('spusteni-behu')
    expect(article.find('table.md-table').exists()).toBe(true)
    expect(wrapper.text()).toContain('Spuštění běhu')
    expect(wrapper.get('[data-test="guide-previous"]').attributes('href')).toBe('#/guide/uvod')
  })

  it('searches all chapters', async () => {
    go('#/guide')
    api()
    const wrapper = mountGuide(); await flushPromises()
    await wrapper.get('[data-test="guide-search"]').setValue('tlacitko')
    const hits = wrapper.findAll('[data-test="guide-hit"]')
    expect(hits.map((h) => h.attributes('href'))).toEqual(['#/guide/backlog/spusteni-behu'])
    await wrapper.get('[data-test="guide-search"]').setValue('nic takoveho')
    expect(wrapper.get('[data-test="guide-hits"]').text()).toContain('Nic nenalezeno')
  })

  it('shows a failed load', async () => {
    go('#/guide')
    api(false)
    const wrapper = mountGuide(); await flushPromises()
    expect(wrapper.get('[data-test="guide-error"]').text()).toContain('nejde to')
  })

  it('loads English and switches both ways without losing a search or section URL', async () => {
    setLocale('en')
    go('#/guide/backlog/spusteni-behu')
    const fetchMock = api()
    const wrapper = mountGuide(); await flushPromises()
    let search = wrapper.get<HTMLInputElement>('[data-test="guide-search"]')
    expect(fetchMock).toHaveBeenCalledWith('/api/guide?locale=en', expect.anything())
    expect(search.attributes('aria-label')).toBe('Search the guide')
    expect(wrapper.get('[data-test="guide-article"] h2').text()).toBe('Starting a run')
    expect(wrapper.get('[data-test="guide-article"] h2').attributes('id')).toBe('spusteni-behu')
    await search.setValue('unfinished search')
    setLocale('cs'); await flushPromises()
    search = wrapper.get<HTMLInputElement>('[data-test="guide-search"]')
    expect(search.element.value).toBe('unfinished search')
    expect(search.attributes('aria-label')).toBe('Hledat v příručce')
    expect(wrapper.get('[data-test="guide-article"] h2').text()).toBe('Spuštění běhu')
    expect(window.location.hash).toBe('#/guide/backlog/spusteni-behu')
    setLocale('en'); await flushPromises()
    search = wrapper.get<HTMLInputElement>('[data-test="guide-search"]')
    expect(search.element.value).toBe('unfinished search')
    expect(wrapper.get('[data-test="guide-hits"]').text()).toBe('Nothing found.')
    expect(wrapper.get('[data-test="guide-article"] h2').attributes('id')).toBe('spusteni-behu')
  })

  it.each(['en', 'cs'] as const)('localizes loading and API failures in %s, retaining technical details', async (language) => {
    setLocale(language)
    go('#/guide')
    const pending = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn(() => pending.promise))
    const wrapper = mountGuide()
    expect(wrapper.text()).toBe(language === 'en' ? 'Loading guide…' : 'Načítám příručku…')
    pending.resolve(new Response(JSON.stringify({ ok: false, error: { code: 'boom', message: 'ENOENT /guide' } }), { status: 500 }))
    await flushPromises()
    const failure = wrapper.get('[data-test="guide-error"]')
    expect(failure.text()).toContain(language === 'en' ? 'Could not load the guide.' : 'Příručku se nepodařilo načíst.')
    expect(failure.get('summary').text()).toBe(language === 'en' ? 'Technical details' : 'Technické podrobnosti')
    expect(failure.get('details').text()).toContain('ENOENT /guide')
  })

  it.each(['resolve', 'reject'] as const)('ignores a stale locale request that later %ss', async (settle) => {
    go('#/guide')
    const stale = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('=cs') ? stale.promise : Promise.resolve(response(EN_CHAPTERS))))
    const wrapper = mountGuide()
    setLocale('en'); await flushPromises()
    if (settle === 'resolve') stale.resolve(response())
    else stale.reject(new Error('stale error'))
    await flushPromises()
    expect(wrapper.get('[data-test="guide-article"]').text()).toContain('What is GIRO.')
    expect(wrapper.find('[data-test="guide-error"]').exists()).toBe(false)
  })
})


it('translates guide controls and document while keeping the query and chapter', async () => {
  go('#/guide/backlog')
  const fetchMock = api()
  const wrapper = mountGuide()
  await flushPromises()
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
    expect(wrapper.get('[data-test="guide-article"] h2').text()).toBe(language === 'en' ? 'Starting a run' : 'Spuštění běhu')
    expect(wrapper.get('article').attributes('lang')).toBe(language)
  }
  expect(fetchMock).toHaveBeenCalledTimes(3)
})

it('localizes a failed guide request after changing language', async () => {
  const fetchMock = api(false)
  const wrapper = mountGuide()
  await flushPromises()
  for (const [language, message] of [['en', 'Could not load the guide.'], ['cs', 'Příručku se nepodařilo načíst.']] as const) {
    setLocale(language)
    await flushPromises()
    expect(wrapper.get('[data-test="guide-error"]').text()).toContain(message)
    expect(wrapper.get('[data-test="guide-error"] details').text()).toContain('nejde to')
  }
  expect(fetchMock).toHaveBeenCalledTimes(3)
})
