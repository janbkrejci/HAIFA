// Guard: the dashboard uses its own ConfirmDialog, Tooltip and SelectMenu, never the
// browser's system dialogs, native tooltips or native selects.
import { describe, expect, it } from 'vitest'

const sources = import.meta.glob<string>('/src/**/*.{vue,ts}', {
  query: '?raw',
  import: 'default',
  eager: true,
})

const files = Object.entries(sources).filter(([path]) => !path.endsWith('.test.ts'))

describe('no native dialogs or tooltips', () => {
  it('scans the sources', () => {
    expect(files.length).toBeGreaterThan(10)
  })

  it.each(files)('%s calls no system dialog', (_path, source) => {
    expect(source).not.toMatch(/window\.(confirm|alert|prompt)\b/)
    expect(source).not.toMatch(/(?<![\w.$])(alert|prompt)\s*\(/)
  })

  it.each(files.filter(([path]) => path.endsWith('.vue')))('%s has no native tooltip', (_path, source) => {
    const template = source.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '')
    expect(template).not.toMatch(/<title[\s>]/)
    // These components consume `title` as a heading prop and render no title attribute.
    const tags = template.match(/<[A-Za-z][^>]*?\s:?title=/g) ?? []
    for (const tag of tags) expect(tag).toMatch(/^<(DetailSection|ConfirmDialog|PlanView|UncommittedBanner)\b/)
  })

  it.each(files.filter(([path]) => path.endsWith('.vue')))('%s has no native select', (_path, source) => {
    const template = source.replace(/<script[\s\S]*?<\/script>/g, '').replace(/<style[\s\S]*?<\/style>/g, '')
    expect(template).not.toMatch(/<select[\s>]/)
    // <datalist> suggestions of a text input are allowed: they are not a select.
    expect(template.replace(/<datalist[\s\S]*?<\/datalist>/g, '')).not.toMatch(/<option[\s>]/)
  })
})
