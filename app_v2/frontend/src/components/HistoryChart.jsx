/**
 * HistoryChart — the app's actual point: production vs. consumption over
 * time, bold in the foreground. The gap between them (production surplus)
 * is what drives curtailment — this chart is meant to make that gap
 * visible at a glance, not to catalog every source. Individual sources
 * still render, but muted in the background by default; a toggle brings
 * them forward for anyone who wants the breakdown.
 *
 * Areas are overlaid, not stacked, for the same reason established
 * earlier: a stacked bottom series only shows its own value while
 * everything above it shows a cumulative sum, so the dominant source
 * (Nucléaire, ~70%) would structurally read as the smallest line.
 */
import { useMemo, useState } from 'react'
import {
  ComposedChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  bioenergies: '#84cc16',
  thermique:   '#ef4444',
}
const SOURCE_LABELS = {
  nucleaire:   'Nucléaire',
  eolien:      'Éolien',
  solaire:     'Solaire',
  hydraulique: 'Hydraulique',
  bioenergies: 'Bioénergies',
  thermique:   'Thermique fossile',
}
const PROD_COLOR  = '#2dd4bf'
const CONSO_COLOR = '#f59e0b'

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function transformData(data) {
  return data.map(r => ({
    timestamp: formatTs(r.timestamp),
    total: Object.values(r.sources || {}).reduce((s, v) => s + (v > 0 ? v : 0), 0),
    conso: r.consommation_mw ?? null,
    ...r.sources,
  }))
}

/** Sources ordered by total magnitude, largest first — drives the legend's reading order. */
function deriveAllSources(chartData) {
  const totals = new Map()
  for (const row of chartData) {
    for (const key of Object.keys(SOURCE_COLORS)) {
      const val = row[key]
      if (typeof val === 'number') totals.set(key, (totals.get(key) || 0) + val)
    }
  }
  return Array.from(totals.keys()).sort((a, b) => totals.get(b) - totals.get(a))
}

const tooltipStyle = {
  contentStyle: {
    background: 'var(--color-surface-2)',
    border: '1px solid var(--color-border)',
    borderRadius: '8px',
  },
  labelStyle: { color: 'var(--color-text)' },
}

/** @param {{ data: Array, region: string, loading?: boolean }} props */
export function HistoryChart({ data, region, loading = false }) {
  const [showSources, setShowSources] = useState(false)

  if (loading) {
    return (
      <div className="glass-card chart-card" data-testid="history-chart-loading">
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </div>
    )
  }

  if (!region) return null

  if (!data.length) {
    return (
      <section className="glass-card chart-card chart-empty" data-testid="history-chart-empty">
        <h2 className="chart-title">Production &amp; consommation — {region}</h2>
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="4,17 9,10 13,13 20,5" />
            </svg>
          </span>
          <p className="empty-state__title">Aucune donnée pour cette région</p>
          <p className="empty-state__hint">
            Le pipeline se lance toutes les 15 min.<br />
            Modifiez la plage de dates ou attendez le prochain cycle.
          </p>
        </div>
      </section>
    )
  }

  const chartData = transformData(data)
  const sources   = deriveAllSources(chartData)
  const sourceOpacity = showSources ? { fill: 0.18, stroke: 1 } : { fill: 0.04, stroke: 0.22 }

  return (
    <section className="glass-card chart-card" data-testid="history-chart">
      <div className="chart-title-row">
        <h2 className="chart-title">Production &amp; consommation — {region}</h2>
        <button
          type="button"
          className={`btn btn-ghost btn-xs${showSources ? ' btn-ghost--active' : ''}`}
          onClick={() => setShowSources(v => !v)}
          title="Afficher le détail par source de production, en fond"
        >
          {showSources ? 'Masquer le détail' : 'Détail par source'}
        </button>
      </div>

      <div style={{ flex: '1 1 0', minHeight: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ComposedChart data={chartData} margin={{ top: 8, right: 48, left: 0, bottom: 0 }}>
          <defs>
            {sources.map(src => (
              <linearGradient key={src} id={`hgrad-${src}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={SOURCE_COLORS[src] || '#888'} stopOpacity={sourceOpacity.fill} />
                <stop offset="95%" stopColor={SOURCE_COLORS[src] || '#888'} stopOpacity={sourceOpacity.fill * 0.15} />
              </linearGradient>
            ))}
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.2} />
          <XAxis dataKey="timestamp" tick={{ fill: '#9a9a9e', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#9a9a9e', fontSize: 11 }} unit=" MW" width={44} />
          <Tooltip {...tooltipStyle} />
          <Legend
            content={() => (
              <ul className="history-legend">
                <li className="history-legend__item">
                  <span className="history-legend__dot" style={{ background: PROD_COLOR }} />
                  Production totale
                </li>
                <li className="history-legend__item">
                  <span className="history-legend__dot" style={{ background: CONSO_COLOR }} />
                  Consommation
                </li>
                {showSources && sources.map(src => (
                  <li key={src} className="history-legend__item history-legend__item--muted">
                    <span className="history-legend__dot" style={{ background: SOURCE_COLORS[src] || '#888' }} />
                    {SOURCE_LABELS[src] || src}
                  </li>
                ))}
              </ul>
            )}
          />

          {/* Individual sources — muted background by default, in fixed
              largest-first order so smaller lines still draw on top. */}
          {sources.map(src => (
            <Area
              key={src}
              type="monotone"
              dataKey={src}
              stroke={SOURCE_COLORS[src] || '#888'}
              strokeOpacity={sourceOpacity.stroke}
              strokeWidth={1}
              fill={`url(#hgrad-${src})`}
              isAnimationActive={false}
            />
          ))}

          {/* Production totale + Consommation — bold foreground lines, the
              actual point of the chart: the gap between them is surplus. */}
          <Line type="monotone" dataKey="total" stroke={PROD_COLOR} strokeWidth={2.5} dot={false} isAnimationActive={false} name="Production totale" />
          <Line type="monotone" dataKey="conso" stroke={CONSO_COLOR} strokeWidth={2.5} strokeDasharray="6 3" dot={false} isAnimationActive={false} name="Consommation" />
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </section>
  )
}
