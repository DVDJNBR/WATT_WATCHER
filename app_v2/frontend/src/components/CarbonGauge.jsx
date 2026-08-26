/**
 * CarbonGauge — Story 5.1, Task 2.3
 *
 * Radial gauge showing carbon intensity (gCO₂/kWh) derived from
 * the energy mix. Green = low carbon, red = high.
 * AC #1: Carbon intensity displayed.
 */
import { RadialBarChart, RadialBar, PolarAngleAxis, ResponsiveContainer } from 'recharts'

const MAX_INTENSITY = 600  // gCO₂/kWh — grid max for France scale

/** Emission factors (gCO₂eq/kWh) — simplified IPCC medians */
const EMISSION_FACTORS = {
  nucleaire:   12,
  eolien:      11,
  hydraulique: 24,
  solaire:     48,
  bioenergies: 230,
  gaz:         490,
  fioul:       733,
  charbon:     820,
}

/**
 * Compute a weighted-average carbon intensity from a sources object.
 * @param {Record<string,number>} sources  { nucleaire: 450, eolien: 300, ... }
 * @returns {number} gCO₂/kWh
 */
export function computeCarbonIntensity(sources) {
  let totalMw = 0
  let weightedCo2 = 0

  for (const [source, mw] of Object.entries(sources)) {
    if (typeof mw !== 'number' || mw <= 0) continue
    const factor = EMISSION_FACTORS[source] ?? 0
    totalMw += mw
    weightedCo2 += mw * factor
  }

  if (totalMw === 0) return 0
  return Math.round(weightedCo2 / totalMw)
}

function intensityColor(intensity) {
  if (intensity < 100) return '#10b981'   // green — very low
  if (intensity < 250) return '#84cc16'   // lime
  if (intensity < 400) return '#f59e0b'   // amber
  return '#ef4444'                        // red — high
}

function intensityLabel(intensity) {
  if (intensity < 100) return 'Très faible'
  if (intensity < 250) return 'Faible'
  if (intensity < 400) return 'Moyen'
  return 'Élevé'
}

/** @param {{ sources: Record<string,number>, loading?: boolean }} props */
export function CarbonGauge({ sources = {}, loading = false }) {
  const intensity = computeCarbonIntensity(sources)
  const color = intensityColor(intensity)
  const chartData = [{ value: Math.min(intensity, MAX_INTENSITY), fill: color }]

  return (
    <section className="glass-card chart-card" data-testid="carbon-gauge">
      <h2 className="chart-title">Intensité carbone</h2>

      {loading ? (
        <div className="skeleton" style={{ height: '200px' }} data-testid="carbon-gauge-skeleton" />
      ) : (
        <>
          <ResponsiveContainer width="100%" height={200}>
            <RadialBarChart
              innerRadius="60%"
              outerRadius="90%"
              data={chartData}
              startAngle={180}
              endAngle={0}
            >
              <PolarAngleAxis type="number" domain={[0, MAX_INTENSITY]} tick={false} />
              <RadialBar dataKey="value" cornerRadius={8} background={{ fill: 'rgba(255,255,255,0.05)' }} />
            </RadialBarChart>
          </ResponsiveContainer>

          <div className="carbon-label" data-testid="carbon-value">
            <span className="carbon-number" style={{ color }}>{intensity}</span>
            <span className="carbon-unit"> gCO₂/kWh</span>
            <p className="carbon-badge" style={{ color }}>{intensityLabel(intensity)}</p>
          </div>
        </>
      )}
    </section>
  )
}
