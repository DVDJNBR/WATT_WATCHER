/**
 * TrendKpiCard — headline number + full-width hoverable line, for the
 * "Chiffre" slots in the Power-BI-style fixed layout (map + 2 numbers).
 */
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { useMemo } from 'react'

function normalize(vals) {
  const nums = vals.filter(v => v != null)
  if (!nums.length) return { min: 0, max: 1 }
  const min = Math.min(...nums)
  const max = Math.max(...nums)
  return { min, max: max > min ? max : min + 1 }
}

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
 *
 * With two lines, each is normalized to its OWN min-max before plotting
 * (tooltip still shows the raw value) — a shared linear scale would
 * squeeze both lines into whatever fraction of the range separates their
 * absolute levels (e.g. production sitting ~6000 MW above consommation),
 * so each one's own day-to-day wobble reads as nearly flat even though it
 * isn't. Independent normalization gives both the full sparkline height.
 */
export function TrendKpiCard({
  title, explain, value, unit = '', color = 'var(--color-accent)', sparkData = [], loading = false,
  secondaryColor = null, primaryName = null, secondaryName = null,
}) {
  const plotData = useMemo(() => {
    if (!secondaryColor) return sparkData
    const { min: min1, max: max1 } = normalize(sparkData.map(r => r.v))
    const { min: min2, max: max2 } = normalize(sparkData.map(r => r.v2))
    return sparkData.map(r => ({
      ...r,
      vPlot: r.v != null ? (r.v - min1) / (max1 - min1) : null,
      v2Plot: r.v2 != null ? (r.v2 - min2) / (max2 - min2) : null,
    }))
  }, [sparkData, secondaryColor])

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
                <LineChart data={plotData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                  <Line
                    type="monotone" dataKey={secondaryColor ? 'vPlot' : 'v'} name={primaryName || title}
                    stroke={color} dot={false} strokeWidth={1.5} isAnimationActive={false}
                  />
                  {secondaryColor && (
                    <Line
                      type="monotone" dataKey="v2Plot" name={secondaryName || title}
                      stroke={secondaryColor} dot={false} strokeWidth={1.5} isAnimationActive={false}
                    />
                  )}
                  <Tooltip
                    formatter={(_v, name, entry) => {
                      const raw = entry.dataKey === 'v2Plot' ? entry.payload.v2 : entry.payload.v
                      return [`${Math.round(raw).toLocaleString('fr-FR')} ${unit}`, name]
                    }}
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
