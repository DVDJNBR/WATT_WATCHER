/**
 * PriceTrendChart — day-ahead spot price (EUR/MWh) over time, national.
 *
 * Replaces the redundant pairing of a day-by-day heatmap + a monthly bar
 * count (both were really just two views of the same "how often/how much"
 * negative-price question) with the actual price series — frequency and
 * intensity both read directly off one line: how often it dips below the
 * zero reference, and how far.
 */
import { AreaChart, Area, ReferenceLine, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/** @param {{ data: Array<{timestamp:string, price_eur_mwh:number}>, loading?: boolean }} props */
export function PriceTrendChart({ data = [], loading = false }) {
  const { chartData, zeroOffset } = useMemo(() => {
    const rows = data
      .filter(r => r.price_eur_mwh != null)
      .map(r => ({ timestamp: formatTs(r.timestamp), price: r.price_eur_mwh }))
    const values = rows.map(r => r.price)
    const max = Math.max(0, ...values)
    const min = Math.min(0, ...values)
    // Fraction from the top of the plot area where price = 0 — splits the
    // fill gradient there so positive/negative read as two distinct colors
    // instead of one flat fill straddling the zero line.
    const zeroOffset = max === min ? 0 : max / (max - min)
    return { chartData: rows, zeroOffset }
  }, [data])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="price-trend-loading">
        <h2 className="chart-title">Prix spot — France</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="price-trend-empty">
        <h2 className="chart-title">Prix spot — France</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="price-trend">
      <h2 className="chart-title" title="Prix spot day-ahead (EUR/MWh), France entière — un seul prix national, pas de découpage régional (comme publié par ENTSO-E).">
        Prix spot — France
      </h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="price-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset={0}          stopColor="#2dd4bf" stopOpacity={0.32} />
                <stop offset={zeroOffset} stopColor="#2dd4bf" stopOpacity={0.04} />
                <stop offset={zeroOffset} stopColor="#ef4444" stopOpacity={0.04} />
                <stop offset={1}          stopColor="#ef4444" stopOpacity={0.32} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
            <XAxis dataKey="timestamp" tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit=" €" width={48} />
            <Tooltip
              formatter={v => [`${v.toFixed(2).replace('.', ',')} €/MWh`, 'Prix spot']}
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <ReferenceLine y={0} stroke="var(--color-text-muted)" strokeDasharray="4 4" />
            <Area type="monotone" dataKey="price" stroke="#2dd4bf" fill="url(#price-grad)" strokeWidth={1.5} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
