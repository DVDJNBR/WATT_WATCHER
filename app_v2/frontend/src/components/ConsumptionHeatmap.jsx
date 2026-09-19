/**
 * ConsumptionHeatmap — average consumption by hour-of-day × day-of-week
 * over the selected period, as a heatmap instead of a line chart. A time
 * series over weeks tangles every day's curve together; this collapses
 * that down to the recurring shape itself — when in the day/week
 * consumption actually peaks — which is what "temporalité" means here,
 * not the raw series (already covered by the KPI cards' balance number).
 */
import { useMemo, useState } from 'react'

const DOW_LABELS = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
const HOURS = Array.from({ length: 24 }, (_, i) => i)

function isoWeekday(date) {
  const d = date.getDay() // 0=Sun..6=Sat
  return d === 0 ? 6 : d - 1 // 0=Mon..6=Sun
}

// Dark amber-tinted near-black -> full-saturation amber. A true RGB ramp
// (not an opacity blend into the card background) so the low end actually
// reads as dark instead of washed-out — opacity blending never gets dark
// enough to give the range real amplitude.
const DARK  = [32, 24, 12]
const BRIGHT = [245, 158, 11] // #f59e0b

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

// Normalized against the observed min-max (not 0) — national consumption
// never gets close to 0, so anchoring the ramp there would squeeze the
// entire real day/night swing into a narrow, low-contrast top slice.
function cellColor(v, min, max) {
  if (v == null) return 'var(--color-surface-2)'
  const t = max > min ? Math.min(1, Math.max(0, (v - min) / (max - min))) : 0.5
  const [r, g, b] = DARK.map((c, i) => lerp(c, BRIGHT[i], t))
  return `rgb(${r}, ${g}, ${b})`
}

/** @param {{ data: Array<{timestamp:string, consommation_mw:number}>, loading?: boolean }} props */
export function ConsumptionHeatmap({ data = [], loading = false }) {
  const [hovered, setHovered] = useState(null)

  const { grid, min, max } = useMemo(() => {
    const sums = Array.from({ length: 7 }, () => Array(24).fill(0))
    const counts = Array.from({ length: 7 }, () => Array(24).fill(0))
    for (const r of data) {
      if (r.consommation_mw == null) continue
      const d = new Date(r.timestamp)
      if (isNaN(d)) continue
      const dow = isoWeekday(d)
      const hour = d.getHours()
      sums[dow][hour] += r.consommation_mw
      counts[dow][hour]++
    }
    const g = sums.map((row, dow) => row.map((s, h) => (counts[dow][h] ? s / counts[dow][h] : null)))
    const flat = g.flat().filter(v => v != null)
    return { grid: g, min: Math.min(...flat, Infinity), max: Math.max(0, ...flat) }
  }, [data])

  const hasData = grid.some(row => row.some(v => v != null))

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="consumption-heatmap-loading">
        <h2 className="chart-title">Profil de consommation — jour × heure</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!hasData) {
    return (
      <section className="glass-card chart-card" data-testid="consumption-heatmap-empty">
        <h2 className="chart-title">Profil de consommation — jour × heure</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="consumption-heatmap">
      <h2
        className="chart-title"
        title="Consommation moyenne par heure et jour de la semaine, sur la période sélectionnée — révèle le profil type (pointes du soir, creux du week-end...) plutôt que la série brute."
      >
        Profil de consommation — jour × heure
      </h2>
      <div className="consumption-heatmap">
        <div className="consumption-heatmap__hours">
          {HOURS.map(h => <span key={h}>{h % 3 === 0 ? `${h}h` : ''}</span>)}
        </div>
        {DOW_LABELS.map((label, dow) => (
          <div key={label} className="consumption-heatmap__row">
            <span className="consumption-heatmap__dow">{label}</span>
            <div className="consumption-heatmap__cells">
              {HOURS.map(h => (
                <div
                  key={h}
                  className="consumption-heatmap__cell"
                  style={{ background: cellColor(grid[dow][h], min, max) }}
                  onMouseEnter={e => setHovered({ dow: label, hour: h, v: grid[dow][h], x: e.clientX, y: e.clientY })}
                  onMouseMove={e => hovered && setHovered(h2 => ({ ...h2, x: e.clientX, y: e.clientY }))}
                  onMouseLeave={() => setHovered(null)}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {hovered && (
        <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 40 }}>
          <strong>{hovered.dow} — {hovered.hour}h</strong>
          <span className="map-tooltip__value">
            {hovered.v != null ? `${Math.round(hovered.v).toLocaleString('fr-FR')} MW` : 'Pas de donnée'}
          </span>
        </div>
      )}
    </section>
  )
}
