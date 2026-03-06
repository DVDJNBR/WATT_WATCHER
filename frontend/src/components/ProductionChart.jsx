/**
 * ProductionChart — Story 5.1, Task 2.2
 *
 * Stacked area chart showing energy production by source over time.
 * AC #1: Displays production per source.
 * AC #2: Updates when region changes.
 * Uses recharts AreaChart.
 */
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'

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
  nucleaire:   'Nucléaire',
  eolien:      'Éolien',
  solaire:     'Solaire',
  hydraulique: 'Hydraulique',
  gaz:         'Gaz',
  bioenergies: 'Bioénergies',
  charbon:     'Charbon',
  fioul:       'Fioul',
}

/**
 * Transform API records into recharts-compatible data.
 * @param {Array} records - data array from the production API
 * @returns {Array}
 */
export function transformProductionData(records) {
  return records.map(r => ({
    timestamp: new Date(r.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }),
    ...r.sources,
  }))
}

/**
 * Derive the union of all source keys across every record.
 * Ensures sources appearing in later records are not missed.
 * @param {Array} chartData - transformed data rows
 * @returns {string[]}
 */
function deriveAllSources(chartData) {
  const seen = new Set()
  for (const row of chartData) {
    for (const key of Object.keys(row)) {
      if (key !== 'timestamp') seen.add(key)
    }
  }
  return Array.from(seen)
}

/** @param {{ data: Array, loading?: boolean, error?: string|null }} props */
export function ProductionChart({ data, loading = false, error = null }) {
  if (loading) {
    return (
      <div className="glass-card chart-card" data-testid="production-chart-loading">
        <div className="skeleton" style={{ height: '300px' }} />
      </div>
    )
  }

  if (error) {
    return (
      <div className="glass-card chart-card chart-error" data-testid="production-chart-error">
        <p>Erreur de chargement : {error}</p>
      </div>
    )
  }

  if (!data.length) {
    return (
      <section className="glass-card chart-card chart-empty" data-testid="production-chart-empty">
        <h2 className="chart-title">Production par source (MW)</h2>
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">📊</span>
          <p className="empty-state__title">Aucune donnée disponible</p>
          <p className="empty-state__hint">
            Le pipeline se lance toutes les 15 min.<br />
            Modifiez la plage de dates ou attendez le prochain cycle.
          </p>
        </div>
      </section>
    )
  }

  const chartData = transformProductionData(data)
  const sources = deriveAllSources(chartData)

  return (
    <section className="glass-card chart-card" data-testid="production-chart">
      <h2 className="chart-title">Production par source (MW)</h2>
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <defs>
            {sources.map(source => (
              <linearGradient key={source} id={`grad-${source}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%"  stopColor={SOURCE_COLORS[source] || '#888'} stopOpacity={0.4} />
                <stop offset="95%" stopColor={SOURCE_COLORS[source] || '#888'} stopOpacity={0.05} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#888888" strokeOpacity={0.2} />
          <XAxis dataKey="timestamp" tick={{ fill: '#8b9ab5', fontSize: 11 }} />
          <YAxis tick={{ fill: '#8b9ab5', fontSize: 11 }} unit=" MW" width={70} />
          <Tooltip
            contentStyle={{
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-border)',
              borderRadius: '8px',
            }}
            labelStyle={{ color: 'var(--color-text)' }}
          />
          <Legend formatter={name => SOURCE_LABELS[name] || name} />
          {sources.map(source => (
            <Area
              key={source}
              type="monotone"
              dataKey={source}
              stackId="1"
              stroke={SOURCE_COLORS[source] || '#888'}
              fill={`url(#grad-${source})`}
              strokeWidth={2}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </section>
  )
}
