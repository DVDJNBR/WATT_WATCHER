/**
 * MeteoChart — temperature and wind speed over time for a region.
 *
 * Data comes from GET /v1/meteo/regional (fact_meteo Gold table,
 * sourced from Open-Meteo free API).
 */
import {
  ComposedChart, Line, Bar, Area,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer,
} from 'recharts'
import { useMemo } from 'react'

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
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
export function MeteoChart({ data = [], region, loading = false }) {
  const chartData = useMemo(() =>
    [...data]
      .sort((a, b) => a.timestamp < b.timestamp ? -1 : 1)
      .map(r => ({
        timestamp: formatTs(r.timestamp),
        temperature_c:  r.temperature_c  != null ? +r.temperature_c.toFixed(1)  : null,
        wind_speed_10m: r.wind_speed_10m != null ? +r.wind_speed_10m.toFixed(1) : null,
        cloudcover_pct: r.cloudcover_pct != null ? Math.round(r.cloudcover_pct) : null,
      })),
    [data]
  )

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="meteo-chart-loading">
        <h2 className="chart-title">Météo — {region || 'France'}</h2>
        <div className="skeleton" style={{ height: 240 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="meteo-chart-empty">
        <h2 className="chart-title">Météo — {region || 'France'}</h2>
        <div className="empty-state">
          <span className="empty-state__icon" aria-hidden="true">🌡️</span>
          <p className="empty-state__title">Pas encore de données météo</p>
          <p className="empty-state__hint">Lancez le pipeline pour ingérer les données Open-Meteo.</p>
        </div>
      </section>
    )
  }

  const hasWind  = chartData.some(r => r.wind_speed_10m != null)
  const hasCloud = chartData.some(r => r.cloudcover_pct  != null)

  return (
    <section className="glass-card chart-card" data-testid="meteo-chart">
      <h2 className="chart-title">Météo — {region || 'France'}</h2>

      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={chartData} margin={{ top: 8, right: 60, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
          <XAxis
            dataKey="timestamp"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            interval="preserveStartEnd"
          />
          {/* Left Y-axis: temperature */}
          <YAxis
            yAxisId="temp"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
            unit="°C"
            width={50}
          />
          {/* Right Y-axis: wind speed + cloudcover (0–100) */}
          <YAxis
            yAxisId="right"
            orientation="right"
            tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
            width={60}
            domain={[0, 100]}
          />
          <Tooltip {...tooltipStyle} />
          <Legend />

          {/* Cloudcover area (background, behind wind) */}
          {hasCloud && (
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="cloudcover_pct"
              fill="#94a3b8"
              fillOpacity={0.15}
              stroke="#94a3b8"
              strokeWidth={1}
              dot={false}
              name="Nébulosité (%)"
            />
          )}

          {/* Wind bars */}
          {hasWind && (
            <Bar
              yAxisId="right"
              dataKey="wind_speed_10m"
              fill="#60a5fa"
              fillOpacity={0.4}
              name="Vent 10m (km/h)"
              maxBarSize={8}
            />
          )}

          {/* Temperature line (on top) */}
          <Line
            yAxisId="temp"
            type="monotone"
            dataKey="temperature_c"
            stroke="#f97316"
            strokeWidth={2}
            dot={false}
            name="Température (°C)"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </section>
  )
}
