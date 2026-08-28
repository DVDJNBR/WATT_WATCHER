/**
 * JsonBlock — pretty-printed JSON with lightweight syntax coloring.
 * `compact` tightens font-size/line-height for use inside small preview
 * panels (e.g. the Pipeline diagram's Bronze stage).
 */
const TOKEN_RE = /("(\\u[a-fA-F0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function highlightLine(line) {
  return escapeHtml(line).replace(TOKEN_RE, (match) => {
    let cls = 'json-number'
    if (/^"/.test(match)) cls = /:$/.test(match) ? 'json-key' : 'json-string'
    else if (/^(true|false)$/.test(match)) cls = 'json-bool'
    else if (match === 'null') cls = 'json-null'
    return `<span class="${cls}">${match}</span>`
  })
}

export function JsonBlock({ data, compact = false }) {
  const html = JSON.stringify(data, null, 2)
    .split('\n')
    .map(line => `<span class="json-line">${highlightLine(line)}</span>`)
    .join('\n')

  const cls = 'content-codeblock json-block' + (compact ? ' json-block--compact' : '')
  return <pre className={cls} dangerouslySetInnerHTML={{ __html: html }} />
}
