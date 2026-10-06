/**
 * PreviewPanel — format-appropriate content for a pipeline stage: condensed
 * JSON for Bronze, a transposed mini-table for Silver/Gold, a route for API.
 * Tables are transposed (one row per column, name left / value right)
 * because one row of real data read sideways is as wide as the sum of its
 * headers — transposed, it's the width of the longest name plus value.
 */
import { JsonBlock } from '../JsonBlock.jsx'

function BronzePreview({ preview }) {
  if (preview.kind === 'csv') {
    return <pre className="content-codeblock">{preview.header}{'\n'}{preview.row}</pre>
  }
  return <JsonBlock data={preview.data} compact />
}

function MiniTable({ table, columns, row, caption = false }) {
  return (
    <table className="pipeline-table">
      {caption && <caption>{table}</caption>}
      <tbody>
        {columns.map((c, i) => (
          <tr key={c}>
            <th scope="row">{c}</th>
            <td>{String(row[i])}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TablePreview({ preview }) {
  return <MiniTable {...preview} />
}

// StarPreview — Gold's data isn't one flat row, it's a fact table resolved
// against its dimensions. Shown as a cluster (fact + its dims), not linked
// by crow's-foot lines to a specific key: a connector draws block-to-block,
// not key-to-key, so the precise FK lines from the original mockup don't
// carry over — the grouping alone still says "these belong together".
function StarPreview({ preview }) {
  return (
    <div className="pipeline-star">
      <MiniTable {...preview.fact} caption />
      <div className="pipeline-star__dims">
        {preview.dims.map(dim => <MiniTable key={dim.table} {...dim} caption />)}
      </div>
    </div>
  )
}

function ApiPreview({ preview }) {
  const [verb, path] = preview.route.split(' ')
  return (
    <pre className="content-codeblock pipeline-route">
      <span className="pipeline-http-verb">{verb}</span> {path}
    </pre>
  )
}

const RENDERERS = { json: BronzePreview, csv: BronzePreview, table: TablePreview, star: StarPreview, api: ApiPreview }

export function PreviewPanel({ source, stageKind }) {
  const preview = source.previews[stageKind]
  if (!preview) return null

  const Renderer = RENDERERS[preview.kind]
  return <Renderer preview={preview} />
}
