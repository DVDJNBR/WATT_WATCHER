/**
 * NegativePriceTrend — monthly total hours at negative price, bar chart.
 * Complements the day-by-day calendar heatmap with a trend-over-months view.
 */
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'

const MONTH_LABELS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']

/** @param {{ days: Array<{date:string, n_slots:number}>, loading?: boolean }} props */
export function NegativePriceTrend({ days = [], loading = false }) {
  const chartData = useMemo(() => {
    const byMonth = new Map()
    for (const d of days) {
      if (!d.n_slots) continue
      const date = new Date(d.date + 'T00:00:00')
      const key = `${date.getFullYear()}-${date.getMonth()}`
      const hours = (byMonth.get(key)?.hours || 0) + d.n_slots * 0.25
      byMonth.set(key, { label: `${MONTH_LABELS[date.getMonth()]} ${date.getFullYear()}`, hours, sortKey: date.getFullYear() * 12 + date.getMonth() })
    }
    return Array.from(byMonth.values()).sort((a, b) => a.sortKey - b.sortKey)
  }, [days])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="negative-price-trend-loading">
        <h2 className="chart-title">Heures à prix négatif, par mois</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="negative-price-trend-empty">
        <h2 className="chart-title">Heures à prix négatif, par mois</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="negative-price-trend">
      <h2 className="chart-title" title="Total d'heures à prix négatif par mois — fait ressortir la tendance saisonnière (surplus renouvelable au printemps/été) que le calendrier jour par jour ne montre pas directement.">Heures à prix négatif, par mois</h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
            <XAxis dataKey="label" tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} />
            <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit="h" width={40} />
            <Tooltip
              formatter={v => [`${v.toFixed(1)} h`, 'À prix négatif']}
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <Bar dataKey="hours" fill="#2dd4bf" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
