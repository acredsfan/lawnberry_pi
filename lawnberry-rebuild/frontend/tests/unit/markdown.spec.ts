import { describe, it, expect } from 'vitest'
import { renderMarkdownSafe } from '@/utils/markdown'

describe('renderMarkdownSafe', () => {
  it('renders basic markdown to HTML', () => {
    const html = renderMarkdownSafe('# Title\n\nSome **bold** text and a [link](https://example.com).')
    expect(html).toContain('<h1>')
    expect(html).toContain('<strong>bold</strong>')
    expect(html).toContain('<a')
  })

  it('sanitizes dangerous HTML/script', () => {
    const md = 'Hello<script>alert(1)</script>\n\n<img src=x onerror=alert(2) />'
    const html = renderMarkdownSafe(md)
    // Raw script tags should not appear
    expect(html).not.toContain('<script')
    // Dangerous HTML should be escaped, not executed
    expect(html).toContain('&lt;script&gt;alert(1)&lt;/script&gt;')
    expect(html).toContain('&lt;img src=x onerror=alert(2) /&gt;')
    // And no raw <img> tag should slip through when provided in Markdown source
    expect(html).not.toContain('<img')
  })
})
