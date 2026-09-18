/**
 * MixCategoryChart — production regrouped into 3 categories instead of the
 * raw source list: renouvelable (EnR), nucléaire (bas carbone, pas
 * renouvelable), fossile (thermique — RTE's regional feed only publishes
 * fossil thermal as one combined figure, not split by gaz/charbon/fioul).
 */
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts'
import { useMemo } from 'react'

const RENEWABLE = new Set(['eolien', 'solaire', 'hydraulique', 'bioenergies'])
const FOSSIL = new Set(['thermique', 'gaz', 'charbon', 'fioul'])

const CATEGORY_COLORS = { renouvelable: '#10b981', nucleaire: '#7c3aed', fossile: '#ef4444' }
const CATEGORY_LABELS = { renouvelable: 'Renouvelable', nucleaire: 'Nucléaire', fossile: 'Fossile' }

function formatTs(ts) {
  const d = new Date(ts)
  if (isNaN(d)) return ts
  return d.toLocaleString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

function categorize(sources) {
  let renouvelable = 0, nucleaire = 0, fossile = 0
  for (const [src, mw] of Object.entries(sources || {})) {
    if (typeof mw !== 'number' || mw <= 0) continue
    if (RENEWABLE.has(src)) renouvelable += mw
    else if (src === 'nucleaire') nucleaire += mw
    else if (FOSSIL.has(src)) fossile += mw
  }
  return { renouvelable, nucleaire, fossile }
}

/** @param {{ data: Array, loading?: boolean }} props */
export function MixCategoryChart({ data = [], loading = false }) {
  const chartData = useMemo(() =>
    data.map(r => ({ timestamp: formatTs(r.timestamp), ...categorize(r.sources) })),
    [data]
  )

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="mix-category-loading">
        <h2 className="chart-title">Renouvelable vs nucléaire vs fossile</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="mix-category-empty">
        <h2 className="chart-title">Renouvelable vs nucléaire vs fossile</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="mix-category">
      <h2 className="chart-title" title="Même production, regroupée en 3 grandes familles au lieu de 8 filières : renouvelable, nucléaire (bas carbone mais pas renouvelable), fossile.">Renouvelable vs nucléaire vs fossile</h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
            <defs>
              {Object.entries(CATEGORY_COLORS).map(([key, color]) => (
                <linearGradient key={key} id={`cat-grad-${key}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={color} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={color} stopOpacity={0.05} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} />
            <XAxis dataKey="timestamp" tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} interval="preserveStartEnd" />
            <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit=" MW" width={65} />
            <Tooltip
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <Legend formatter={name => CATEGORY_LABELS[name] || name} />
            {Object.keys(CATEGORY_COLORS).map(key => (
              <Area key={key} type="monotone" dataKey={key} stackId="cat" stroke={CATEGORY_COLORS[key]} fill={`url(#cat-grad-${key})`} strokeWidth={1.5} />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
