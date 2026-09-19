/**
 * TrendKpiCard — headline number + full-width hoverable line, for the
 * "Chiffre" slots in the Power-BI-style fixed layout (map + 2 numbers).
 */
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'

/**
 * @param {{
 *   title: string, explain?: string, value: string|number, unit?: string,
 *   color?: string, sparkData?: Array<{t:string, v:number, v2?:number}>, loading?: boolean,
 *   secondaryColor?: string, primaryName?: string, secondaryName?: string,
 * }} props
 * secondaryColor adds a 2nd line (dataKey "v2") for cards that need to show
 * two related series (e.g. production vs consommation) instead of a single
 * value's trend — the headline number stays whatever the card is titled
 * for; primaryName/secondaryName label the two lines when they aren't the
 * same thing as the card title (e.g. title "Équilibre prod/conso" but the
 * lines are "Production" and "Consommation").
 */
export function TrendKpiCard({
  title, explain, value, unit = '', color = 'var(--color-accent)', sparkData = [], loading = false,
  secondaryColor = null, primaryName = null, secondaryName = null,
}) {
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
                  <Line type="monotone" dataKey="v" name={primaryName || title} stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false} />
                  {secondaryColor && (
                    <Line type="monotone" dataKey="v2" name={secondaryName || title} stroke={secondaryColor} dot={false} strokeWidth={1.5} isAnimationActive={false} />
                  )}
                  <Tooltip
                    formatter={(v, name) => [`${Math.round(v).toLocaleString('fr-FR')} ${unit}`, name]}
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
