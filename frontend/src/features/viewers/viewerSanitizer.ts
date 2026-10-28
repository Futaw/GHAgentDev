import DOMPurify from 'dompurify'

const tags = [
  'article', 'section', 'div', 'nav', 'aside', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li',
  'dl', 'dt', 'dd', 'table', 'caption', 'thead', 'tbody', 'tr', 'th', 'td', 'pre', 'code',
  'strong', 'em', 'span', 'button', 'a',
]
const attributes = [
  'class', 'id', 'role', 'aria-label', 'aria-live', 'aria-busy', 'data-block-type',
  'data-source-reference-id', 'type', 'scope', 'href', 'target', 'rel',
]

export const sanitizeViewerHtml = (html: string) => DOMPurify.sanitize(html, {
  ALLOWED_TAGS: tags,
  ALLOWED_ATTR: attributes,
  ALLOW_DATA_ATTR: false,
})
