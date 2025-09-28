// Safe Markdown rendering utility for Docs Hub
// Uses markdown-it for parsing and DOMPurify for sanitization.
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

// Configure markdown-it with conservative options
const md = new MarkdownIt({
  html: false, // don't allow raw HTML passthrough
  linkify: true,
  breaks: true,
  typographer: true,
})

export function renderMarkdownSafe(src: string): string {
  const rawHtml = md.render(src || '')
  // Sanitize the rendered HTML to prevent XSS
  const clean = DOMPurify.sanitize(rawHtml, {
    USE_PROFILES: { html: true },
  })
  return clean
}

export default { renderMarkdownSafe }
