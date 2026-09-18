/**
 * TrendKpiCard — headline number + full-width hoverable line, for the
 * "Chiffre" slots in the Power-BI-style fixed layout (map + 2 numbers).
 */
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'

/**
 * @param {{
 *   title: string, explain?: string, value: string|number, unit?: string,
 *   color?: string, sparkData?: Array<{t:string, v:number}>, loading?: boolean,
 * }} props
 */
export function TrendKpiCard({ title, explain, value, unit = '', color = 'var(--color-accent)', sparkData = [], loading = false }) {
  return (
    <article className="glass-card trend-kpi-card" data-testid="trend-kpi-card">
      <span className="kpi-title" title={explain}>{title}</span>
      {loading ? (
        <div className="skeleton" style={{ height: '2rem', marginTop: 8 }} />
      ) : (
        <>
          <p className="kpi-value">{value}{unit && <span className="kpi-unit"> {unit}</span>}</p>
          {sparkData.length > 1 && (
            <div className="trend-kpi-card__chart">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={sparkData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                  <Line type="monotone" dataKey="v" stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
                  <Tooltip
                    formatter={v => [`${Math.round(v).toLocaleString('fr-FR')} ${unit}`, title]}
                    labelFormatter={l => l}
                    contentStyle={{ background: 'var(--color-surface-2)', border: '1px solid var(--color-border)', fontSize: 11, borderRadius: 6 }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </>
      )}
    </article>
  )
}
