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

function MiniTable({ table, columns, row }) {
  return (
    <table className="content-table content-table--stats preview-panel__table preview-panel__table--mini">
      <caption>{table}</caption>
      <thead>
        <tr>{columns.map(c => <th key={c}>{c}</th>)}</tr>
      </thead>
      <tbody>
        <tr>{row.map((v, i) => <td key={i}>{String(v)}</td>)}</tr>
      </tbody>
    </table>
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

// StarPreview — Gold's data isn't one flat row, it's a fact table resolved
// against its dimensions. Shown as a cluster (fact + its dims), not linked
// by crow's-foot lines to a specific key: a connector draws block-to-block,
// not key-to-key, so the precise FK lines from the original mockup don't
// carry over — the grouping alone still says "these belong together".
function StarPreview({ preview }) {
  return (
    <div className="preview-panel__star">
      <MiniTable {...preview.fact} />
      <div className="preview-panel__star-dims">
        {preview.dims.map(dim => <MiniTable key={dim.table} {...dim} />)}
      </div>
    </div>
  )
}

function ApiPreview({ preview }) {
  return (
    <p className="preview-panel__route">
      <span className="method-badge">GET</span>
      <code>{preview.route.replace(/^GET /, '')}</code>
    </p>
  )
}

const RENDERERS = { json: BronzePreview, csv: BronzePreview, table: TablePreview, star: StarPreview, api: ApiPreview }

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
