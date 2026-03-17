/**
 * CapacityChart — installed capacity by source for a region.
 *
 * Data comes from GET /v1/capacity/regional (fact_capacity Gold table,
 * sourced from ODRE national registry).
 */
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'

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

const tooltipStyle = {
  contentStyle: {
    background: 'var(--color-surface-2)',
    border: '1px solid var(--color-border)',
    borderRadius: '8px',
    fontSize: '0.8rem',
  },
  labelStyle: { color: 'var(--color-text)', fontWeight: 600 },
}

/** @param {{ data: Array, region?: string, loading?: boolean }} props */
export function CapacityChart({ data = [], region, loading = false }) {
  // Aggregate by source (sum puissance over all years, take latest year per source)
  const chartData = useMemo(() => {
    const bySource = {}
    for (const row of data) {
      const src = row.source
      if (!src) continue
      if (!bySource[src] || (row.annee && (!bySource[src].annee || row.annee > bySource[src].annee))) {
        bySource[src] = row
      }
    }
    return Object.values(bySource)
      .map(r => ({
        source: r.source,
        label: SOURCE_LABELS[r.source] || r.source,
        puissance: r.puissance_installee_mw != null ? Math.round(r.puissance_installee_mw) : 0,
      }))
      .sort((a, b) => b.puissance - a.puissance)
  }, [data])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="capacity-chart-loading">
        <h2 className="chart-title">Capacité installée — {region || 'Région'}</h2>
        <div className="skeleton" style={{ height: 200 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="capacity-chart-empty">
        <h2 className="chart-title">Capacité installée — {region || 'Région'}</h2>
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">⚡</span>
          <p className="empty-state__title">Pas encore de données de capacité</p>
          <p className="empty-state__hint">Lancez le pipeline pour ingérer le registre ODRE.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="capacity-chart">
      <h2 className="chart-title">Capacité installée — {region || 'Région'} (MW)</h2>

      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 32 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            angle={-30}
            textAnchor="end"
          />
          <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit=" MW" width={65} />
          <Tooltip
            {...tooltipStyle}
            formatter={(value) => [`${value.toLocaleString('fr-FR')} MW`, 'Capacité installée']}
          />
          <Bar dataKey="puissance" name="Puissance installée (MW)" radius={[3, 3, 0, 0]}>
            {chartData.map((entry) => (
              <Cell key={entry.source} fill={SOURCE_COLORS[entry.source] || '#888'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </section>
  )
}
