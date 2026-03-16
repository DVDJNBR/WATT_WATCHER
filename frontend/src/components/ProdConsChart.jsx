/**
 * ProdConsChart — production vs consommation line chart.
 *
 * Shows two lines over time:
 *   • Production totale (somme des sources) — bleu accent
 *   • Consommation MW                       — orange ambre
 * Zone shaded rouge quand production > consommation (sur-production).
 */
import {
  ComposedChart, Line, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

/**
 * Compute a dynamic insight title from the latest data.
 * e.g. "Sur-production depuis 14h45" or "Équilibre prod/conso"
 */
function buildInsightTitle(chartData, region) {
  const base = region ? `Production — ${region}` : 'Production — France'
  if (!chartData.length) return base

  const last = chartData[chartData.length - 1]
  if (last.conso == null || last.conso === 0) return base

  const THRESHOLD = 0.05  // ±5% = équilibre
  const ratio = (last.prod - last.conso) / last.conso

  let state  // 'surplus' | 'deficit' | 'balanced'
  if (ratio > THRESHOLD)       state = 'surplus'
  else if (ratio < -THRESHOLD) state = 'deficit'
  else                         state = 'balanced'

  if (state === 'balanced') return `Équilibre prod/conso${region ? ` — ${region}` : ' — France'}`

  // Walk backwards to find when the current state started
  let sinceIdx = chartData.length - 1
  for (let i = chartData.length - 2; i >= 0; i--) {
    const r = chartData[i]
    if (r.conso == null || r.conso === 0) break
    const rRatio = (r.prod - r.conso) / r.conso
    const rState = rRatio > THRESHOLD ? 'surplus' : rRatio < -THRESHOLD ? 'deficit' : 'balanced'
    if (rState !== state) break
    sinceIdx = i
  }

  const sinceTs = chartData[sinceIdx].rawTs
  const sinceTime = sinceTs
    ? new Date(sinceTs).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
    : null

  const label = state === 'surplus' ? 'Sur-production' : 'Sous-production'
  const suffix = sinceTime ? ` depuis ${sinceTime}` : ''
  return `${label}${suffix}${region ? ` — ${region}` : ' — France'}`
}

function buildChartData(data) {
  return data.map(r => {
    const prod = Math.round(
      Object.values(r.sources || {}).reduce((s, v) => s + (v > 0 ? v : 0), 0)
    )
    const conso = r.consommation_mw != null ? Math.round(r.consommation_mw) : null
    // surplusZone: zone rouge quand prod > conso
    const surplusZone = (conso != null && prod > conso) ? prod : null
    return { timestamp: formatTs(r.timestamp), rawTs: r.timestamp, prod, conso, surplusZone }
  })
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

function CustomLegend() {
  return (
    <div style={{ display: 'flex', gap: 16, justifyContent: 'center', fontSize: '0.8rem', paddingTop: 8 }}>
      <span style={{ color: '#4f8ef7' }}>⎯ Production</span>
      <span style={{ color: '#f59e0b' }}>⎯ Consommation</span>
      <span style={{ color: '#ef4444', opacity: 0.7 }}>▪ Sur-production</span>
    </div>
  )
}

/** @param {{ data: Array, region?: string, loading?: boolean }} props */
export function ProdConsChart({ data = [], region, loading = false }) {
  const chartData = useMemo(() => buildChartData(data), [data])
  const hasConsommation = chartData.some(r => r.conso != null)
  const title = useMemo(() => buildInsightTitle(chartData, region), [chartData, region])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="prod-cons-chart-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ height: 320 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="prod-cons-chart-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">📊</span>
          <p className="empty-state__title">Aucune donnée disponible</p>
          <p className="empty-state__hint">Rafraîchissez le pipeline ou élargissez la plage de dates.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="prod-cons-chart"
      aria-label={`Graphique ${title}`}>
      <h2 className="chart-title">{title}</h2>

      <ResponsiveContainer width="100%" height={320}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="surplusGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor="#ef4444" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#ef4444" stopOpacity={0.05} />
            </linearGradient>
          </defs>

          <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
            unit=" MW"
            width={70}
          />
          <Tooltip {...tooltipStyle} />

          {/* Zone rouge sur-production */}
          {hasConsommation && (
            <Area
              type="monotone"
              dataKey="surplusZone"
              fill="url(#surplusGrad)"
              stroke="none"
              name="Sur-production"
              legendType="none"
              activeDot={false}
            />
          )}

          {/* Ligne consommation */}
          {hasConsommation && (
            <Line
              type="monotone"
              dataKey="conso"
              stroke="#f59e0b"
              strokeWidth={2}
              dot={false}
              name="Consommation"
              strokeDasharray="6 3"
            />
          )}

          {/* Ligne production */}
          <Line
            type="monotone"
            dataKey="prod"
            stroke="#4f8ef7"
            strokeWidth={2.5}
            dot={false}
            name="Production"
          />
        </ComposedChart>
      </ResponsiveContainer>

      <CustomLegend />
    </section>
  )
}
