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

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map(c => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

// Dark neutral -> full-saturation `color`, scaled by each bar's value
// relative to the group's min-max — a flat single color makes every bar
// read as "equally important" even though the whole point of a ranking is
// to show who's ahead; light/dark amplitude does that at a glance, same
// logic as the heatmap next to it.
const DARK = [32, 30, 28]
function magnitudeColor(v, min, max, rgb) {
  const t = max > min ? Math.min(1, Math.max(0, (v - min) / (max - min))) : 1
  const [r, g, b] = DARK.map((c, i) => lerp(c, rgb[i], 0.25 + t * 0.75))
  return `rgb(${r}, ${g}, ${b})`
}

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
  const colorRgb = useMemo(() => hexToRgb(color), [color])
  const [minVal, maxVal] = useMemo(() => {
    const vals = chartData.map(d => d.value)
    return vals.length ? [Math.min(...vals), Math.max(...vals)] : [0, 0]
  }, [chartData])

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
              {chartData.map(d => (
                <Cell key={d.code_insee} fill={magnitudeColor(d.value, minVal, maxVal, colorRgb)} />
              ))}
              <LabelList dataKey="value" position="right" formatter={v => `${valueFormatter(v)}${unit}`} fill="var(--color-text-muted)" fontSize={10} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
