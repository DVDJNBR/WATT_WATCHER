/**
 * HistoryChart — production vs. consumption over time.
 * Sources are always visible in the background; total prod + conso
 * are the two bold foreground lines. The gap between them is surplus.
 */
import { useMemo, useState, useEffect } from 'react'
import {
  ComposedChart, Area, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
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
const PROD_COLOR = '#2dd4bf'

function useDarkTheme() {
  const [dark, setDark] = useState(() => {
    const t = document.documentElement.getAttribute('data-theme')
    if (t === 'dark') return true
    if (t === 'light') return false
    return window.matchMedia('(prefers-color-scheme:dark)').matches
  })
  useEffect(() => {
    const mo = new MutationObserver(() => {
      const t = document.documentElement.getAttribute('data-theme')
      setDark(t === 'dark' || (t !== 'light' && window.matchMedia('(prefers-color-scheme:dark)').matches))
    })
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
    return () => mo.disconnect()
  }, [])
  return dark
}

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
    timeZone: 'UTC',
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
  const isDark = useDarkTheme()
  const consoColor = isDark ? '#e8e8e6' : '#1c1b1a'

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
  const sourceOpacity = { fill: 0.25, stroke: 0.90 }

  return (
    <section className="glass-card chart-card" data-testid="history-chart">
      <h2 className="chart-title">Production &amp; consommation — {region}</h2>

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

          <Line type="monotone" dataKey="total" stroke={PROD_COLOR} strokeWidth={1.5} dot={false} isAnimationActive={false} name="Production totale" />
          <Line type="monotone" dataKey="conso" stroke={consoColor} strokeWidth={1.5} strokeDasharray="6 3" dot={false} isAnimationActive={false} name="Consommation" />
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </section>
  )
}
