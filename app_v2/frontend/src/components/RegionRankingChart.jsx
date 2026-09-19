/**
 * RegionRankingChart — generic ranked horizontal bar, one bar per region.
 *
 * Unlike a per-region *production* share (skewed by where large plants
 * happen to be metered, not by regional behavior), consumption is a
 * genuinely regional number — it's tied to where people and industry
 * actually draw power, not to plant siting. Used by the Consommation tab
 * to rank regions by current draw.
 */
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Cell, ResponsiveContainer, LabelList } from 'recharts'
import { useMemo } from 'react'

/**
 * @param {{
 *   data: Array<{code_insee:string, region:string, value:number}>,
 *   title: string,
 *   explain?: string,
 *   unit?: string,
 *   color?: string,
 *   valueFormatter?: (v:number) => string,
 *   loading?: boolean,
 * }} props
 */
export function RegionRankingChart({
  data = [],
  title,
  explain,
  unit = '',
  color = '#2dd4bf',
  valueFormatter = v => Math.round(v).toLocaleString('fr-FR'),
  loading = false,
}) {
  const chartData = useMemo(() => [...data].sort((a, b) => b.value - a.value), [data])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="region-ranking-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!chartData.length) {
    return (
      <section className="glass-card chart-card" data-testid="region-ranking-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="region-ranking">
      <h2 className="chart-title" title={explain}>{title}</h2>
      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} layout="vertical" margin={{ top: 4, right: 40, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} horizontal={false} />
            <XAxis type="number" unit={unit} tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }} />
            <YAxis type="category" dataKey="region" width={110} tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} />
            <Tooltip
              formatter={v => [`${valueFormatter(v)}${unit}`, title]}
              contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', borderRadius: 8, fontSize: '0.8rem' }}
              labelStyle={{ color: 'var(--color-text)', fontWeight: 600 }}
            />
            <Bar dataKey="value" radius={[0, 4, 4, 0]} isAnimationActive={false} maxBarSize={18}>
              {chartData.map(d => <Cell key={d.code_insee} fill={color} fillOpacity={0.85} />)}
              <LabelList dataKey="value" position="right" formatter={v => `${valueFormatter(v)}${unit}`} fill="var(--color-text-muted)" fontSize={10} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
