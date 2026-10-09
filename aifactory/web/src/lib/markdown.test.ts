import { describe, expect, it } from 'vitest'
import { renderMarkdown, stripComments } from './markdown'

describe('renderMarkdown', () => {
  it('escapes raw HTML so it never executes', () => {
    const html = renderMarkdown('Ahoj <script>x()</script> a <img src=x onerror=y>')
    expect(html).not.toContain('<script')
    expect(html).not.toContain('<img')
    expect(html).toContain('&lt;script&gt;')
  })

  it('drops single-line and multi-line HTML comments', () => {
    const html = renderMarkdown('před <!-- doplňuje HAIFA --> po\n\n<!--\nskryté\nřádky\n-->\nkonec')
    expect(html).not.toContain('doplňuje')
    expect(html).not.toContain('skryté')
    expect(html).not.toContain('&lt;!--')
    expect(html).toContain('před')
    expect(html).toContain('po')
    expect(html).toContain('konec')
  })

  it('keeps comments inside fenced code verbatim', () => {
    const html = renderMarkdown('```\n<!-- v kódu -->\n```')
    expect(html).toBe('<pre class="md-code"><code>&lt;!-- v kódu --&gt;</code></pre>')
  })

  it('renders headings, lists, code and inline code', () => {
    expect(renderMarkdown('## Nadpis')).toBe('<h2>Nadpis</h2>')
    expect(renderMarkdown('- a\n- b')).toBe('<ul><li>a</li><li>b</li></ul>')
    expect(renderMarkdown('1. x')).toBe('<ol><li>x</li></ol>')
    expect(renderMarkdown('```sh\njust test\n```')).toBe('<pre class="md-code"><code>just test</code></pre>')
    expect(renderMarkdown('use `k`')).toBe('<p>use <code>k</code></p>')
  })

  it('links only http(s)', () => {
    expect(renderMarkdown('[x](https://a.b)')).toContain('<a href="https://a.b"')
    expect(renderMarkdown('[x](javascript:void(0))')).not.toContain('<a')
  })
})

describe('stripComments', () => {
  it('drops a line that is only a comment', () => {
    expect(stripComments(['a', '<!-- c -->', 'b'])).toEqual(['a', 'b'])
  })

  it('swallows the rest after an unclosed comment', () => {
    expect(stripComments(['a', '<!-- c', 'b'])).toEqual(['a'])
  })
})
