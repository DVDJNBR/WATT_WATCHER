/**
 * CarbonBadge — Story 6.2
 *
 * Compact CO₂ intensity badge with colour-coded threshold + mini sparkline.
 * Replaces the radial CarbonGauge per BMAD UX spec.
 *
 * Colors: green < 100, lime < 250, amber < 400, red ≥ 400 gCO₂/kWh
 */
import { LineChart, Line, ResponsiveContainer, Tooltip } from 'recharts'
import { computeCarbonIntensity } from './CarbonGauge.jsx'

export { computeCarbonIntensity }

function intensityColor(v) {
  if (v < 100) return '#10b981'
  if (v < 250) return '#84cc16'
  if (v < 400) return '#f59e0b'
  return '#ef4444'
}

function intensityLabel(v) {
  if (v < 100) return 'Très faible'
  if (v < 250) return 'Faible'
  if (v < 400) return 'Moyen'
  return 'Élevé'
}

/**
 * @param {{
 *   intensity: number,
 *   sparkData: Array<{t: string, v: number}>,
 *   loading?: boolean,
 * }} props
 */
export function CarbonBadge({ intensity = 0, sparkData = [], loading = false }) {
  const color = intensityColor(intensity)

  return (
    <div className="glass-card carbon-badge-card" data-testid="carbon-badge">
      {loading ? (
        <div className="skeleton" style={{ height: 88 }} data-testid="carbon-badge-skeleton" />
      ) : (
        <>
          <p className="carbon-badge__label">Intensité CO₂</p>
          <div className="carbon-badge__row">
            <span className="carbon-badge__number" style={{ color }}>{intensity}</span>
            <span className="carbon-badge__unit">gCO₂/kWh</span>
            <span className="carbon-badge__tag" style={{ background: color + '26', color }}>
              {intensityLabel(intensity)}
            </span>
          </div>
          {sparkData.length > 1 && (
            <ResponsiveContainer width="100%" height={36}>
              <LineChart data={sparkData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
                <Line
                  type="monotone"
                  dataKey="v"
                  stroke={color}
                  dot={false}
                  strokeWidth={1.5}
                  isAnimationActive={false}
                />
                <Tooltip
                  formatter={v => [`${v} gCO₂/kWh`, 'CO₂']}
                  labelFormatter={l => l}
                  contentStyle={{
                    background: 'var(--color-surface-2)',
                    border: '1px solid var(--color-border)',
                    fontSize: 11,
                    borderRadius: 6,
                  }}
                />
              </LineChart>
            </ResponsiveContainer>
          )}
        </>
      )}
    </div>
  )
}
