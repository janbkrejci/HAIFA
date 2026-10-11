import { describe, expect, it } from 'vitest'
import { fold, search, sections, slug, type GuideChapter } from './guide'

const CHAPTERS: GuideChapter[] = [
  { id: 'backlog', title: 'Backlog', markdown: '# Backlog\n\nÚvod.\n\n## Spuštění běhu\n\nTlačítko **Spustit**.\n\n```\n## není nadpis\n```\n\n## Závislosti\n\nPole `depends_on`.\n' },
  { id: 'review', title: 'Review', markdown: '# Review\n\n## Schválení\n\nSchválení PR spustí merge.\n' },
]

describe('guide', () => {
  it('folds diacritics and builds slugs', () => {
    expect(fold('Spuštění Běhu')).toBe('spusteni behu')
    expect(slug('Spuštění běhu')).toBe('spusteni-behu')
    expect(slug('`factory check` a co dál?')).toBe('factory-check-a-co-dal')
  })

  it('splits a chapter at level-2 headings outside code', () => {
    const parts = sections(CHAPTERS[0]!.markdown)
    expect(parts.map((s) => s.id)).toEqual(['', 'spusteni-behu', 'zavislosti'])
    expect(parts[1]!.text).toContain('## není nadpis')
  })

  it('finds sections holding every word, without diacritics', () => {
    const hits = search(CHAPTERS, 'spusteni tlacitko')
    expect(hits.map((h) => [h.chapter.id, h.section.id])).toEqual([['backlog', 'spusteni-behu']])
    expect(search(CHAPTERS, 'merge').map((h) => h.section.id)).toEqual(['schvaleni'])
    expect(search(CHAPTERS, '  ')).toEqual([])
    expect(search(CHAPTERS, 'neexistuje')).toEqual([])
  })
})
