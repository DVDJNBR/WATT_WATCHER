/**
 * EnergySankey — flow diagram: sources -> Production totale -> Consommation
 * France / Export net -> Export net splits by border country.
 *
 * All three stages are measured independently (source mix, national
 * consumption, cross-border physical flow) and don't sum to the exact same
 * total — stage 2 and 3 are proportionally rescaled to the stage-1 total so
 * ribbon widths stay visually consistent, same convention professional
 * energy Sankeys (Eurostat, LLNL) use when reconciling independent metering.
 */
import { useMemo, useState } from 'react'

const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  gaz:         '#ef4444',
  bioenergies: '#84cc16',
  charbon:     '#6b7280',
  fioul:       '#f97316',
}
const SOURCE_LABELS = {
  nucleaire: 'Nucléaire', eolien: 'Éolien', solaire: 'Solaire', hydraulique: 'Hydraulique',
  gaz: 'Gaz', bioenergies: 'Bioénergies', charbon: 'Charbon', fioul: 'Fioul',
}
const SOURCE_ORDER = ['nucleaire', 'eolien', 'solaire', 'hydraulique', 'gaz', 'bioenergies', 'charbon', 'fioul']

const NEUTRAL_NODE = '#8a8378'
const CONSO_COLOR = '#b8b3a8'
const EXPORT_COLOR = '#22d3ee'
const BORDER_COLORS = { GB: '#a78bfa', CH: '#f472b6', IT: '#fb923c', ES: '#facc15' }

const H = 300, GAP = 4, TOP = 16
const X = { left: [40, 82], mid: [230, 270], right: [420, 460], far: [620, 660] }

function ribbonPath(x0, y0a, y0b, x1, y1a, y1b) {
  const xm = (x0 + x1) / 2
  return `M ${x0},${y0a} C ${xm},${y0a} ${xm},${y1a} ${x1},${y1a} L ${x1},${y1b} C ${xm},${y1b} ${xm},${y0b} ${x0},${y0b} Z`
}

function fmtMw(mw) {
  if (mw == null) return '—'
  return `${Math.round(mw).toLocaleString('fr-FR')} MW`
}

/**
 * @param {{
 *   sourceTotals: Record<string, number>,   // MW summed/averaged over the period
 *   consommationTotal: number,
 *   borderTotals: Array<{border_code:string, border_label:string, net_mwh:number}>,
 *   loading?: boolean,
 * }} props
 */
export function EnergySankey({ sourceTotals = {}, consommationTotal = 0, borderTotals = [], loading = false }) {
  const [hover, setHover] = useState(null)

  const geom = useMemo(() => {
    const sources = SOURCE_ORDER
      .map(k => ({ key: k, value: sourceTotals[k] || 0 }))
      .filter(s => s.value > 0)
    const total = sources.reduce((s, r) => s + r.value, 0)
    if (total <= 0) return null

    const availH = H - GAP * (sources.length - 1)
    const minFrac = 0.02
    const fracs = sources.map(s => Math.max(s.value / total, minFrac))
    const fracSum = fracs.reduce((a, b) => a + b, 0)
    const heights = fracs.map(f => (f / fracSum) * availH)

    // stage 1: left source nodes (with gaps) -> mid sub-segments (no gaps)
    let y = TOP
    const leftY = []
    for (const h of heights) { leftY.push([y, y + h]); y += h + GAP }
    const midTop = TOP, midBot = midTop + availH
    let y2 = midTop
    const midY = []
    for (const h of heights) { midY.push([y2, y2 + h]); y2 += h }

    const stage1 = sources.map((s, i) => ({
      key: s.key, color: SOURCE_COLORS[s.key], label: SOURCE_LABELS[s.key], value: s.value,
      d: ribbonPath(X.left[1], leftY[i][0], leftY[i][1], X.mid[0], midY[i][0], midY[i][1]),
    }))
    const leftNodes = sources.map((s, i) => ({ key: s.key, color: SOURCE_COLORS[s.key], label: SOURCE_LABELS[s.key], value: s.value, y0: leftY[i][0], y1: leftY[i][1] }))

    // stage 2: reconcile conso/export against the real (measured) total
    const exportTotal = Math.max(0, borderTotals.reduce((s, b) => s + Math.max(0, b.net_mwh || 0), 0))
    const rawConso = Math.max(0, consommationTotal)
    const rawTotal = rawConso + exportTotal
    const consoMw = rawTotal > 0 ? (rawConso / rawTotal) * total : total * 0.8
    const exportMw = total - consoMw
    const consoH = availH * (consoMw / total)
    const exportH = availH * (exportMw / total)

    const stage2 = [
      { key: 'consommation', color: CONSO_COLOR, opacity: 0.55, label: 'Consommation France', value: consoMw,
        d: ribbonPath(X.mid[1], midTop, midTop + consoH, X.right[0], midTop, midTop + consoH) },
      { key: 'export', color: EXPORT_COLOR, opacity: 0.6, label: 'Export net', value: exportMw,
        d: ribbonPath(X.mid[1], midTop + consoH + GAP, midBot, X.right[0], midTop + consoH + GAP, midBot) },
    ]
    const midNode = { x0: X.mid[0], x1: X.mid[1], y0: midTop, y1: midBot, value: total }
    const rightNodes = [
      { key: 'consommation', color: CONSO_COLOR, label: 'Consommation France', value: consoMw, y0: midTop, y1: midTop + consoH },
      { key: 'export', color: EXPORT_COLOR, label: 'Export net', value: exportMw, y0: midTop + consoH + GAP, y1: midBot },
    ]

    // stage 3: export net -> per-border split (only positive net exporters shown)
    const positiveBorders = borderTotals.filter(b => (b.net_mwh || 0) > 0)
    const posSum = positiveBorders.reduce((s, b) => s + b.net_mwh, 0) || 1
    let y3 = midTop + consoH + GAP
    const stage3 = []
    const farNodes = []
    for (const b of positiveBorders) {
      const h = exportH * (b.net_mwh / posSum)
      stage3.push({
        key: b.border_code, color: BORDER_COLORS[b.border_code] || '#94a3b8', opacity: 0.6,
        label: b.border_label, value: b.net_mwh,
        d: ribbonPath(X.right[1], y3, y3 + h, X.far[0], y3, y3 + h),
      })
      farNodes.push({ key: b.border_code, color: BORDER_COLORS[b.border_code] || '#94a3b8', label: b.border_label, value: b.net_mwh, y0: y3, y1: y3 + h })
      y3 += h
    }

    return { leftNodes, stage1, midNode, stage2, rightNodes, stage3, farNodes, viewW: X.far[1] + 190, viewH: H + TOP + 24 }
  }, [sourceTotals, consommationTotal, borderTotals])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="energy-sankey-loading">
        <h2 className="chart-title">Flux production → consommation / export</h2>
        <div className="skeleton" style={{ height: 320 }} />
      </section>
    )
  }

  if (!geom) {
    return (
      <section className="glass-card chart-card" data-testid="energy-sankey-empty">
        <h2 className="chart-title">Flux production → consommation / export</h2>
        <div className="empty-state">
          <p className="empty-state__title">Pas de données pour cette période</p>
        </div>
      </section>
    )
  }

  const allRibbons = [...geom.stage1, ...geom.stage2, ...geom.stage3]

  return (
    <section className="glass-card chart-card" data-testid="energy-sankey">
      <h2 className="chart-title">Flux production → consommation / export</h2>
      <div style={{ overflowX: 'auto' }}>
        <svg viewBox={`0 0 ${geom.viewW} ${geom.viewH}`} width="100%" style={{ minWidth: 720, height: 'auto' }}>
          {allRibbons.map(r => (
            <path key={r.key} d={r.d} fill={r.color} fillOpacity={hover === r.key ? 0.95 : (r.opacity ?? 0.55)}
              style={{ cursor: 'default', transition: 'fill-opacity 0.15s' }}
              onMouseEnter={() => setHover(r.key)} onMouseLeave={() => setHover(null)} />
          ))}
          {geom.leftNodes.map(n => <rect key={n.key} x={X.left[0]} y={n.y0} width={X.left[1] - X.left[0]} height={n.y1 - n.y0} fill={n.color} />)}
          <rect x={geom.midNode.x0} y={geom.midNode.y0} width={geom.midNode.x1 - geom.midNode.x0} height={geom.midNode.y1 - geom.midNode.y0} fill={NEUTRAL_NODE} />
          {geom.rightNodes.map(n => <rect key={n.key} x={X.right[0]} y={n.y0} width={X.right[1] - X.right[0]} height={n.y1 - n.y0} fill={n.color} />)}
          {geom.farNodes.map(n => <rect key={n.key} x={X.far[0]} y={n.y0} width={X.far[1] - X.far[0]} height={n.y1 - n.y0} fill={n.color} />)}

          {geom.leftNodes.map(n => (
            <text key={n.key} x={X.left[0] - 8} y={(n.y0 + n.y1) / 2} textAnchor="end" dominantBaseline="middle" fontSize="11" fill="#a19c93">
              {n.label} <tspan fill="#6b6863">· {fmtMw(n.value)}</tspan>
            </text>
          ))}
          <text x={(geom.midNode.x0 + geom.midNode.x1) / 2} y={geom.midNode.y0 - 12} textAnchor="middle" fontSize="12" fontWeight="600" fill="#c7c3bc">
            Production totale <tspan fill="#6b6863">· {fmtMw(geom.midNode.value)}</tspan>
          </text>
          {geom.rightNodes.map(n => (
            <text key={n.key} x={X.right[1] + 8} y={(n.y0 + n.y1) / 2} textAnchor="start" dominantBaseline="middle" fontSize="11" fill="#a19c93">
              {n.label} <tspan fill="#6b6863">· {fmtMw(n.value)}</tspan>
            </text>
          ))}
          {geom.farNodes.map(n => (
            <text key={n.key} x={X.far[1] + 8} y={(n.y0 + n.y1) / 2} textAnchor="start" dominantBaseline="middle" fontSize="11" fill="#a19c93">
              {n.label} <tspan fill="#6b6863">· {fmtMw(n.value)}</tspan>
            </text>
          ))}
        </svg>
      </div>
      <p style={{ fontSize: '0.72rem', color: 'var(--color-text-muted)', marginTop: 6 }}>
        Export net réparti sur 4 frontières suivies (Royaume-Uni, Suisse, Italie, Espagne) — zone Core
        (Allemagne/Belgique) non captée pour l'instant.
      </p>
    </section>
  )
}
