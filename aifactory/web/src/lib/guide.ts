// The user and administrator guide (#/guide): chapters from GET /api/guide, their sections
// and a search over them.
import { getGlobal } from './api'

export interface GuideChapter {
  id: string
  title: string
  markdown: string
}

export interface GuideSection {
  /** The slug of the `## ` heading; '' for the text before the first one. */
  id: string
  title: string
  text: string
}

export interface GuideHit {
  chapter: GuideChapter
  section: GuideSection
  snippet: string
}

export async function fetchGuide(): Promise<GuideChapter[]> {
  return (await getGlobal<{ chapters: GuideChapter[] }>('/guide')).chapters
}

/** Lowercase without diacritics, for slugs and search. */
export function fold(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
}

/** URL-safe id of a heading: `Spuštění běhu` → `spusteni-behu`. */
export function slug(title: string): string {
  return fold(title.replaceAll('`', '')).replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
}

/** The chapter split at its `## ` headings (outside fenced code). */
export function sections(markdown: string): GuideSection[] {
  const out: GuideSection[] = [{ id: '', title: '', text: '' }]
  let fence = false
  for (const line of markdown.split('\n')) {
    if (/^\s*```/.test(line)) fence = !fence
    const heading = fence ? null : /^##\s+(.*)$/.exec(line)
    if (heading?.[1] !== undefined) {
      const title = heading[1].trim()
      out.push({ id: slug(title), title, text: '' })
      continue
    }
    const last = out[out.length - 1]
    if (last) last.text += line + '\n'
  }
  return out
}

/** Sections whose title or text holds every word of `query`, with a snippet around the first. */
export function search(chapters: GuideChapter[], query: string): GuideHit[] {
  const words = fold(query).split(/\s+/).filter(Boolean)
  if (!words.length) return []
  const hits: GuideHit[] = []
  for (const chapter of chapters) {
    for (const section of sections(chapter.markdown)) {
      const plain = section.text.replace(/\s+/g, ' ').trim()
      const haystack = fold(`${chapter.title} ${section.title} ${plain}`)
      if (!words.every((word) => haystack.includes(word))) continue
      const first = words[0] ?? ''
      const at = Math.max(0, fold(plain).indexOf(first))
      const start = Math.max(0, at - 60)
      const snippet = (start > 0 ? '…' : '') + plain.slice(start, at + 100) + (at + 100 < plain.length ? '…' : '')
      hits.push({ chapter, section, snippet })
    }
  }
  return hits
}
