/**
 * HistoryChart — production history for a selected region.
 *
 * Shows stacked area (production by source) + total production bold line.
 * Displayed below the France map when a region is selected.
 */
import {
  ComposedChart, Area,
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

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function transformData(data) {
  return data.map(r => ({ timestamp: formatTs(r.timestamp), ...r.sources }))
}

function deriveAllSources(chartData) {
  const seen = new Set()
  for (const row of chartData) {
    for (const key of Object.keys(row)) {
      if (key !== 'timestamp') seen.add(key)
    }
  }
  return Array.from(seen)
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
        <h2 className="chart-title">Historique de production — {region}</h2>
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

  return (
    <section className="glass-card chart-card" data-testid="history-chart">
      <h2 className="chart-title">Historique de production — {region}</h2>

      <div style={{ flex: '1 1 0', minHeight: 0 }}>
      <ResponsiveContainer width="100%" height="100%">
        {/* right:120 (not 60) — MeteoChart reserves an extra 60px for its
            second (right-side) Y-axis that this chart doesn't have; matching
            the total reserved width, not just the margin, keeps both plot
            areas — and their day gridlines — aligned when stacked. */}
        <ComposedChart data={chartData} margin={{ top: 8, right: 120, left: 0, bottom: 0 }}>
          <defs>
            {sources.map(src => (
              <linearGradient key={src} id={`hgrad-${src}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={SOURCE_COLORS[src] || '#888'} stopOpacity={0.35} />
                <stop offset="95%" stopColor={SOURCE_COLORS[src] || '#888'} stopOpacity={0.04} />
              </linearGradient>
            ))}
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.2} />
          <XAxis dataKey="timestamp" tick={{ fill: '#9a9a9e', fontSize: 10 }} interval="preserveStartEnd" />
          <YAxis tick={{ fill: '#9a9a9e', fontSize: 11 }} unit=" MW" width={50} />
          <Tooltip {...tooltipStyle} />
          <Legend
            formatter={name => SOURCE_LABELS[name] || name}
            wrapperStyle={{ fontSize: 10, paddingTop: 4, lineHeight: 1.4 }}
            iconSize={7}
          />

          {/* Stacked areas per source */}
          {sources.map(src => (
            <Area
              key={src}
              type="monotone"
              dataKey={src}
              stackId="sources"
              stroke={SOURCE_COLORS[src] || '#888'}
              fill={`url(#hgrad-${src})`}
              strokeWidth={1.5}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </section>
  )
}
