/**
 * CurtailmentCalendar — headline stats + a GitHub-style calendar heatmap of
 * every day the national market price went negative.
 *
 * The regional bar chart (CurtailmentShareChart) answers "who contributed
 * most" but reads as an abstract percentage with no emotional weight. This
 * answers a more visceral question — "how often, and how bad" — with two
 * numbers anyone can feel (hours at negative price; the record €/MWh) and a
 * pattern (clustering) the grid makes visible at a glance.
 */
import { memo, useMemo, useState } from 'react'

const MS_PER_DAY = 86400000
const MONTH_LABELS = ['janv.', 'févr.', 'mars', 'avr.', 'mai', 'juin', 'juil.', 'août', 'sept.', 'oct.', 'nov.', 'déc.']
const DOW_LABELS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']

function isoWeekday(date) {
  const d = date.getDay() // 0=Sun..6=Sat
  return d === 0 ? 6 : d - 1 // 0=Mon..6=Sun
}

function cellColor(nSlots, maxSlots) {
  if (nSlots === 0) return 'var(--color-surface-2)'
  const t = Math.min(1, nSlots / maxSlots)
  const alpha = 0.25 + t * 0.75
  return `color-mix(in srgb, var(--color-accent) ${Math.round(alpha * 100)}%, var(--color-surface-2))`
}

function formatDateLong(iso) {
  const d = new Date(iso + 'T00:00:00')
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}

/**
 * @param {{
 *   days: Array<{date:string, n_slots:number, min_price:number}>,
 *   range: {start:string, end:string},
 *   stats: {total_days:number, total_hours:number, record_date:string, record_price:number},
 *   loading?: boolean,
 * }} props
 */
export const CurtailmentCalendar = memo(function CurtailmentCalendar({
  days = [],
  range,
  stats,
  loading = false,
}) {
  const [hovered, setHovered] = useState(null)

  const { weeks, monthMarkers, maxSlots } = useMemo(() => {
    if (!range?.start || !range?.end) return { weeks: [], monthMarkers: [], maxSlots: 1 }

    const byDate = new Map(days.map(d => [d.date, d]))
    const start = new Date(range.start + 'T00:00:00')
    const end = new Date(range.end + 'T00:00:00')

    // Pad to the Monday on/before start so every week column has 7 cells
    const padStart = new Date(start)
    padStart.setDate(padStart.getDate() - isoWeekday(start))

    const cells = []
    for (let t = padStart.getTime(); t <= end.getTime(); t += MS_PER_DAY) {
      const d = new Date(t)
      const iso = d.toISOString().slice(0, 10)
      const inRange = d >= start && d <= end
      cells.push({ date: iso, dow: isoWeekday(d), inRange, ...(byDate.get(iso) || { n_slots: 0, min_price: null }) })
    }

    const weeks_ = []
    for (let i = 0; i < cells.length; i += 7) weeks_.push(cells.slice(i, i + 7))

    const markers = []
    let lastMonth = -1
    weeks_.forEach((week, wi) => {
      const firstInRangeCell = week.find(c => c.inRange)
      if (!firstInRangeCell) return
      const m = new Date(firstInRangeCell.date + 'T00:00:00').getMonth()
      if (m !== lastMonth) { markers.push({ week: wi, label: MONTH_LABELS[m] }); lastMonth = m }
    })

    const max = Math.max(1, ...days.map(d => d.n_slots))
    return { weeks: weeks_, monthMarkers: markers, maxSlots: max }
  }, [days, range])

  return (
    <section className="glass-card content-card" data-testid="curtailment-calendar">
      <p className="content-kicker">Prix négatifs — fréquence et intensité</p>

      {loading ? (
        <div className="skeleton" style={{ height: 260, marginTop: 16 }} />
      ) : (
        <>
          <div className="curtailment-stats">
            <div className="curtailment-stat">
              <span className="curtailment-stat__value">{stats.total_hours}h</span>
              <span className="curtailment-stat__label">à prix négatif sur {stats.total_days} jours ({range?.start && formatDateLong(range.start)} → {range?.end && formatDateLong(range.end)})</span>
            </div>
            <div className="curtailment-stat">
              <span className="curtailment-stat__value curtailment-stat__value--record">
                {stats.record_price?.toFixed(2).replace('.', ',')} €/MWh
              </span>
              <span className="curtailment-stat__label">
                record le {stats.record_date && formatDateLong(stats.record_date)} — RTE payait pour qu'on consomme
              </span>
            </div>
          </div>

          <div className="curtailment-calendar-wrap">
            <div className="curtailment-calendar-months">
              {monthMarkers.map(m => (
                <span key={m.week} className="curtailment-calendar-month" style={{ '--week-col': m.week + 1 }}>{m.label}</span>
              ))}
            </div>
            <div className="curtailment-calendar-body">
              <div className="curtailment-calendar-dow">
                {DOW_LABELS.map((l, i) => <span key={i}>{i % 2 === 0 ? l : ''}</span>)}
              </div>
              <div className="curtailment-calendar-grid" style={{ '--n-weeks': weeks.length }}>
                {weeks.map((week, wi) => (
                  <div className="curtailment-calendar-week" key={wi}>
                    {week.map(cell => (
                      <div
                        key={cell.date}
                        className="curtailment-calendar-cell"
                        style={{ background: cell.inRange ? cellColor(cell.n_slots, maxSlots) : 'transparent' }}
                        onMouseEnter={e => cell.inRange && setHovered({ ...cell, x: e.clientX, y: e.clientY })}
                        onMouseMove={e => hovered && setHovered(h => ({ ...h, x: e.clientX, y: e.clientY }))}
                        onMouseLeave={() => setHovered(null)}
                      />
                    ))}
                  </div>
                ))}
              </div>
            </div>
          </div>

          {hovered && (
            <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 52 }}>
              <strong>{formatDateLong(hovered.date)}</strong>
              {hovered.n_slots > 0 ? (
                <>
                  <span className="map-tooltip__value">{hovered.n_slots} créneaux à prix négatif</span>
                  <span style={{ color: '#a1a1aa', fontSize: '0.75rem' }}>min {hovered.min_price?.toFixed(2).replace('.', ',')} €/MWh</span>
                </>
              ) : (
                <span style={{ color: '#a1a1aa', fontSize: '0.75rem' }}>Aucun créneau à prix négatif</span>
              )}
            </div>
          )}
        </>
      )}

      <p className="content-caption">
        Chaque case = un jour. Plus la case est claire, plus il y a eu de créneaux de 15 min à prix
        négatif ce jour-là. Donnée ENTSO-E day-ahead, zone de marché France unique.
      </p>
    </section>
  )
})
