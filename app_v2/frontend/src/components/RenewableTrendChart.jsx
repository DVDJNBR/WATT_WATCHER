/**
 * RenewableTrendChart — part EnR (%) over time, full chart (not a sparkline).
 */
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'
import { computeRenewableShare } from './RenewableShare.jsx'

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** @param {{ data: Array, loading?: boolean }} props */
export function RenewableTrendChart({ data = [], loading = false }) {
  const chartData = useMemo(() =>
    data.map(r => ({ timestamp: formatTs(r.timestamp), share: computeRenewableShare(r.sources || {}) })),
    [data]
  )

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="renewable-trend-loading">
        <h2 className="chart-title">Part EnR dans le temps</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="renewable-trend-empty">
        <h2 className="chart-title">Part EnR dans le temps</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="renewable-trend">
      <h2 className="chart-title" title="Évolution de la part d'énergies renouvelables (éolien, solaire, hydraulique, bioénergies) dans le mix, sur la période sélectionnée.">Part EnR dans le temps</h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
            <XAxis dataKey="timestamp" tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit="%" width={40} domain={[0, 100]} />
            <Tooltip
              formatter={v => [`${v} %`, 'Part EnR']}
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <Line type="monotone" dataKey="share" stroke="#10b981" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
