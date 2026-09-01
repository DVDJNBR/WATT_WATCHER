/**
 * PreviewPanel — format-appropriate content for whichever stage the
 * pipeline diagram's indicator currently sits on: condensed JSON for
 * Bronze, a one-row mini-table for Silver/Gold, a route badge for API.
 */
import { JsonBlock } from '../JsonBlock.jsx'

function BronzePreview({ preview }) {
  if (preview.kind === 'csv') {
    return (
      <>
        <p className="preview-panel__path">{preview.path}</p>
        <pre className="content-codeblock json-block--compact">
          {preview.header}
          {'\n'}
          {preview.row}
        </pre>
      </>
    )
  }
  return (
    <>
      <p className="preview-panel__path">{preview.path}</p>
      <JsonBlock data={preview.data} compact />
    </>
  )
}

function TablePreview({ preview }) {
  return (
    <>
      <p className="preview-panel__path">{preview.table ? `Table : ${preview.table}` : preview.path}</p>
      <div className="preview-panel__table-wrap">
        <table className="content-table content-table--stats preview-panel__table">
          <thead>
            <tr>{preview.columns.map(c => <th key={c}>{c}</th>)}</tr>
          </thead>
          <tbody>
            <tr>{preview.row.map((v, i) => <td key={i}>{String(v)}</td>)}</tr>
          </tbody>
        </table>
      </div>
    </>
  )
}

function ApiPreview({ preview }) {
  // Route name only — no query string, no /v1/ prefix. The full path lives
  // on the Pipeline page's API route list for anyone who wants it.
  const name = preview.route.replace(/^GET /, '').split('?')[0].replace(/^\/v1\//, '')
  return (
    <p className="preview-panel__route">
      <span className="method-badge">GET</span>
      <code>{name}</code>
    </p>
  )
}

const RENDERERS = { json: BronzePreview, csv: BronzePreview, table: TablePreview, api: ApiPreview }

export function PreviewPanel({ source, stageKind }) {
  const preview = source.previews[stageKind]

  if (!preview) {
    return (
      <p className="preview-panel__empty">
        {stageKind === 'dashboard'
          ? 'Cette source alimente le dashboard — clique le nœud pour y aller.'
          : "Pas (encore) exposée à cette étape."}
      </p>
    )
  }

  const Renderer = RENDERERS[preview.kind]
  return (
    <div className="preview-panel__content">
      <Renderer preview={preview} />
    </div>
  )
}
