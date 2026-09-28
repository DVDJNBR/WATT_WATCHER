/**
 * PriceClock — the average spot price of each hour of the day, drawn on a
 * 24-hour dial.
 *
 * The rest of the Prix tab reads left to right on a calendar: one day after
 * another. This one is cyclical on purpose — the question it answers is "at
 * what time of day", not "on what date", and a dial says that before a single
 * label is read. Petal length is the hour's mean price; the red arc inside is
 * the share of that hour's slots that went under zero, which is where the
 * story actually is (no hour has a negative *mean*, but a third of the slots
 * around midday are negative).
 */
import { memo, useMemo, useState } from 'react'

const SIZE = 400
const CX = SIZE / 2
const CY = SIZE / 2
const R_INNER = 62      // zero ring — petals grow outward from here
const R_OUTER = 168
const R_NEG_OUT = 54    // negative-share arcs live inside the ring
const R_NEG_IN = 16

function polar(angleDeg, r) {
  const rad = ((angleDeg - 90) * Math.PI) / 180
  return [CX + r * Math.cos(rad), CY + r * Math.sin(rad)]
}

/** Annular sector path between two angles and two radii. */
function sector(a0, a1, ri, ro) {
  const [x1, y1] = polar(a0, ro)
  const [x2, y2] = polar(a1, ro)
  const [x3, y3] = polar(a1, ri)
  const [x4, y4] = polar(a0, ri)
  const large = a1 - a0 > 180 ? 1 : 0
  return `M${x1} ${y1}A${ro} ${ro} 0 ${large} 1 ${x2} ${y2}L${x3} ${y3}A${ri} ${ri} 0 ${large} 0 ${x4} ${y4}Z`
}

function fmt(v, digits = 1) {
  return v == null ? '—' : v.toFixed(digits).replace('.', ',')
}

/** Mean price, extremes and negative share for each hour of the day. */
function buildHours(data) {
  const buckets = Array.from({ length: 24 }, () => ({ sum: 0, n: 0, min: Infinity, max: -Infinity, neg: 0 }))
  for (const r of data) {
    const v = r.price_eur_mwh
    if (v == null) continue
    const d = new Date(String(r.timestamp).replace(' ', 'T'))
    if (isNaN(d)) continue
    const b = buckets[d.getUTCHours()]
    b.sum += v
    b.n += 1
    if (v < b.min) b.min = v
    if (v > b.max) b.max = v
    if (v < 0) b.neg += 1
  }
  return buckets
    .map((b, h) => (b.n ? {
      h,
      mean: b.sum / b.n,
      min: b.min,
      max: b.max,
      negPct: (100 * b.neg) / b.n,
    } : null))
    .filter(Boolean)
}

/** @param {{ data: Array<{timestamp:string, price_eur_mwh:number}>, loading?: boolean }} props */
export const PriceClock = memo(function PriceClock({ data = [], loading = false }) {
  const [hovered, setHovered] = useState(null)
  const hours = useMemo(() => buildHours(data), [data])

  const title = 'Horloge des prix'
  const explain = "Prix spot moyen de chaque heure de la journée, sur tout l'historique disponible. La longueur du pétale est le prix moyen, l'arc rouge à l'intérieur la part des créneaux de cette heure-là passés sous 0 €/MWh."

  if (loading) {
    return (
      <section className="glass-card chart-card price-clock" data-testid="price-clock-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!hours.length) {
    return (
      <section className="glass-card chart-card price-clock" data-testid="price-clock-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  const maxMean = Math.max(...hours.map(h => h.mean))
  const maxNeg = Math.max(...hours.map(h => h.negPct), 1)
  const trough = hours.reduce((a, b) => (b.mean < a.mean ? b : a))
  const peak = hours.reduce((a, b) => (b.mean > a.mean ? b : a))
  const shown = hovered ?? null

  // Two reference rings, rounded to something sayable rather than to the data's
  // own maximum — a ring labelled "137 €" reads as noise.
  const ringValues = [50, 100].filter(v => v < maxMean)
  const radiusFor = v => R_INNER + (v / maxMean) * (R_OUTER - R_INNER)

  return (
    <section className="glass-card chart-card price-clock" data-testid="price-clock">
      <h2 className="chart-title" title={explain}>{title}</h2>

      <div className="price-clock__dial">
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} role="img" aria-label="Prix moyen par heure de la journée">
          {ringValues.map(v => (
            <g key={v}>
              <circle cx={CX} cy={CY} r={radiusFor(v)} className="price-clock__ring" />
              <text x={CX + 4} y={CY - radiusFor(v) - 4} className="price-clock__ringlabel">{v} €</text>
            </g>
          ))}
          <circle cx={CX} cy={CY} r={R_INNER} className="price-clock__ring price-clock__ring--zero" />

          {hours.map(h => {
            const a0 = h.h * 15 + 1.4
            const a1 = (h.h + 1) * 15 - 1.4
            const r = radiusFor(h.mean)
            const isHot = shown?.h === h.h
            return (
              <g key={h.h}>
                <path
                  d={sector(a0, a1, R_INNER, r)}
                  className={`price-clock__petal${isHot ? ' price-clock__petal--on' : ''}`}
                  style={{ opacity: 0.32 + 0.62 * (h.mean / maxMean) }}
                  onPointerEnter={() => setHovered(h)}
                  onPointerLeave={() => setHovered(null)}
                />
                {h.negPct > 0.5 && (
                  <path
                    d={sector(a0, a1, R_NEG_OUT - (h.negPct / maxNeg) * (R_NEG_OUT - R_NEG_IN), R_NEG_OUT)}
                    className="price-clock__neg"
                    style={{ opacity: 0.35 + 0.6 * (h.negPct / maxNeg) }}
                  />
                )}
              </g>
            )
          })}

          {[0, 6, 12, 18].map(h => {
            const [x, y] = polar(h * 15 + 7.5, R_OUTER + 18)
            return (
              <text key={h} x={x} y={y + 4} textAnchor="middle" className="price-clock__hour">
                {String(h).padStart(2, '0')}h
              </text>
            )
          })}
        </svg>
      </div>

      <p className="price-clock__readout" aria-live="polite">
        {shown ? (
          <>
            <strong>{shown.h}h</strong> — moyenne <strong>{fmt(shown.mean)} €/MWh</strong>,{' '}
            {fmt(shown.negPct)} % des créneaux sous 0 €, extrêmes {fmt(shown.min)} / {fmt(shown.max)} €
          </>
        ) : (
          <>
            Creux à <strong>{trough.h}h</strong> ({fmt(trough.mean)} €, {fmt(trough.negPct)} % sous 0 €) ·
            pic à <strong>{peak.h}h</strong> ({fmt(peak.mean)} €)
          </>
        )}
      </p>
    </section>
  )
})
