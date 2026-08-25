/**
 * JsonBlock — pretty-printed JSON with lightweight syntax coloring.
 * `dropKeys` dims + strikes through the lines for fields that don't
 * survive the cleaning step, to show what actually gets kept.
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

export function JsonBlock({ data, dropKeys = [] }) {
  const lines = JSON.stringify(data, null, 2).split('\n')
  const html = lines
    .map(line => {
      const keyMatch = line.match(/^\s*"(\w+)"\s*:/)
      const dropped = keyMatch && dropKeys.includes(keyMatch[1])
      const cls = 'json-line' + (dropped ? ' json-line--dropped' : '')
      return `<span class="${cls}">${highlightLine(line)}</span>`
    })
    .join('\n')

  return <pre className="content-codeblock json-block" dangerouslySetInnerHTML={{ __html: html }} />
}
