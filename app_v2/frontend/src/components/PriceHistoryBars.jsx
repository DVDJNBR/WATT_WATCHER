/**
 * PriceHistoryBars — day-ahead spot price over the whole available history,
 * one bar per day rising above and falling below the zero line.
 *
 * The 15-min series is far too dense to read over three months, so each day
 * is reduced to what actually matters commercially: how high the price got
 * (bar up), how far below zero it went (bar down), and where it sat on
 * average (the line). The two dashed traits mark the all-time high and the
 * all-time low and carry their value in the label, so the extremes are
 * readable without hovering anything.
 */
import { memo, useMemo } from 'react'
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'

const UP_COLOR = '#2dd4bf'
const DOWN_COLOR = '#ef4444'

// Pixels of clear space either side of the zero line. Without it the up bar
// and the down bar of a mixed day meet, and the pair reads as one green bar
// with a red bite taken out of it rather than as two facts about that day.
const ZERO_GUTTER = 2

/**
 * Bar shape that stops short of the zero line instead of resting on it.
 *
 * recharts hands a negative `height` (with `y` on the zero line) for the
 * downward half of the stack, so the sign has to be normalised here — an
 * earlier version tested `height > 0` and silently dropped every negative
 * day from the chart.
 */
function GutterBar({ x, y, width, height, fill, downward }) {
  const w = Math.abs(width || 0)
  const h0 = Math.abs(height || 0)
  if (!(h0 > 0) || !(w > 0)) return null
  const top = height < 0 ? y + height : y
  const h = Math.max(0.6, h0 - ZERO_GUTTER)
  return <rect x={x} y={downward ? top + ZERO_GUTTER : top} width={w} height={h} fill={fill} />
}

/** Day key in UTC — the same frame every other chart on the dashboard plots in. */
function dayKey(ts) {
  const d = new Date(ts.replace(' ', 'T'))
  if (isNaN(d)) return String(ts).slice(0, 10)
  return d.toISOString().slice(0, 10)
}

function fmtEur(v, digits = 0) {
  if (v == null) return '—'
  return `${v.toFixed(digits).replace('.', ',')} €`
}

function fmtDayShort(iso) {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', timeZone: 'UTC' })
}

function fmtDayLong(iso) {
  const d = new Date(iso + 'T00:00:00Z')
  return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

/** Reduce the raw 15-min series to one row per day. */
function buildDailyRows(data) {
  const byDay = new Map()
  for (const r of data) {
    const v = r.price_eur_mwh
    if (v == null) continue
    const k = dayKey(r.timestamp)
    let d = byDay.get(k)
    if (!d) { d = { day: k, min: v, max: v, sum: 0, n: 0, negSlots: 0 }; byDay.set(k, d) }
    if (v < d.min) d.min = v
    if (v > d.max) d.max = v
    d.sum += v
    d.n += 1
    if (v < 0) d.negSlots += 1
  }
  return Array.from(byDay.values())
    .sort((a, b) => (a.day < b.day ? -1 : 1))
    .map(d => ({
      day: d.day,
      // Bars are anchored on zero: the up bar is how high the day got, the
      // down bar how far below zero it went. A day that never went negative
      // simply has no down bar (and vice versa).
      up: d.max > 0 ? d.max : 0,
      down: d.min < 0 ? d.min : 0,
      mean: d.sum / d.n,
      min: d.min,
      max: d.max,
      negHours: d.negSlots / 4,
    }))
}

function PriceTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="map-tooltip" style={{ position: 'static' }}>
      <strong>{fmtDayLong(row.day)}</strong>
      <span className="map-tooltip__value" style={{ color: UP_COLOR }}>
        max {fmtEur(row.max, 2)}/MWh
      </span>
      <span style={{ fontSize: '0.75rem' }}>moyenne {fmtEur(row.mean, 2)}/MWh</span>
      <span style={{ fontSize: '0.75rem', color: row.min < 0 ? DOWN_COLOR : undefined }}>
        min {fmtEur(row.min, 2)}/MWh
      </span>
      {row.negHours > 0 && (
        <span style={{ fontSize: '0.75rem', color: '#a1a1aa' }}>
          {row.negHours.toString().replace('.', ',')} h à prix négatif
        </span>
      )}
    </div>
  )
}

/**
 * @param {{
 *   data: Array<{timestamp:string, price_eur_mwh:number}>,
 *   loading?: boolean,
 * }} props
 */
export const PriceHistoryBars = memo(function PriceHistoryBars({ data = [], loading = false }) {
  const { rows, hi, lo } = useMemo(() => {
    const rows_ = buildDailyRows(data)
    if (!rows_.length) return { rows: [], hi: null, lo: null }
    const hi_ = rows_.reduce((a, b) => (b.max > a.max ? b : a))
    const lo_ = rows_.reduce((a, b) => (b.min < a.min ? b : a))
    return { rows: rows_, hi: hi_, lo: lo_ }
  }, [data])

  // A dashed line drawn across three months of bars reads as a threshold that
  // means something all along its length. It doesn't — it marks one day. So
  // each trait is a stub around its own record instead.
  const traitFor = useMemo(() => (record, key) => {
    if (!rows.length || !record) return null
    const i = rows.findIndex(r => r.day === record.day)
    if (i < 0) return null
    const half = Math.max(3, Math.round(rows.length * 0.06))
    const from = rows[Math.max(0, i - half)].day
    const to = rows[Math.min(rows.length - 1, i + half)].day
    return [{ x: from, y: record[key] }, { x: to, y: record[key] }]
  }, [rows])

  const title = 'Prix spot — France'
  const explain = 'Prix spot day-ahead (EUR/MWh), France entière. Une barre par jour : vers le haut le prix le plus élevé atteint, vers le bas le plus bas prix négatif. La ligne est la moyenne du jour.'

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="price-history-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="glass-card chart-card" data-testid="price-history-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  // ~8 date ticks whatever the span, so a 3-month history stays readable.
  const tickInterval = Math.max(0, Math.ceil(rows.length / 8) - 1)

  return (
    <section className="glass-card chart-card" data-testid="price-history">
      <div className="price-hero__head">
        <h2 className="chart-title" title={explain}>{title}</h2>
        <div className="price-hero__extremes">
          <span className="price-extreme price-extreme--up">
            <span className="price-extreme__value">{fmtEur(hi.max, 2)}/MWh</span>
            <span className="price-extreme__label">plus haut · {fmtDayShort(hi.day)}</span>
          </span>
          <span className="price-extreme price-extreme--down">
            <span className="price-extreme__value">{fmtEur(lo.min, 2)}/MWh</span>
            <span className="price-extreme__label">plus bas · {fmtDayShort(lo.day)}</span>
          </span>
        </div>
      </div>

      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 10, right: 62, left: 0, bottom: 0 }} barCategoryGap="12%">
            <defs>
              {/* Each bar carries its own gradient box, so both fills are
                  strongest at the extreme end and fade back towards zero. */}
              <linearGradient id="price-bar-up" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={UP_COLOR} stopOpacity={0.95} />
                <stop offset="100%" stopColor={UP_COLOR} stopOpacity={0.25} />
              </linearGradient>
              <linearGradient id="price-bar-down" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={DOWN_COLOR} stopOpacity={0.25} />
                <stop offset="100%" stopColor={DOWN_COLOR} stopOpacity={0.95} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} vertical={false} />
            <XAxis
              dataKey="day"
              tickFormatter={fmtDayShort}
              interval={tickInterval}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              unit=" €"
              width={52}
              tickLine={false}
            />
            <Tooltip content={<PriceTooltip />} cursor={{ fill: 'var(--color-text)', fillOpacity: 0.06 }} />

            {/* stackId keeps both bars on the same x slot; recharts stacks the
                positive value upward and the negative one downward from 0.
                The custom shape opens a gutter so they stay two marks. */}
            <Bar
              dataKey="up" stackId="amp" fill="url(#price-bar-up)" isAnimationActive={false}
              shape={props => <GutterBar {...props} />}
            />
            <Bar
              dataKey="down" stackId="amp" fill="url(#price-bar-down)" isAnimationActive={false}
              shape={props => <GutterBar {...props} downward />}
            />

            <Line
              type="monotone" dataKey="mean" dot={false} isAnimationActive={false}
              stroke="var(--color-text)" strokeWidth={1.25} strokeOpacity={0.85}
            />

            <ReferenceLine y={0} stroke="var(--color-text-muted)" strokeOpacity={0.7} />
            {traitFor(hi, 'max') && (
              <ReferenceLine
                segment={traitFor(hi, 'max')} stroke={UP_COLOR} strokeWidth={1.5} strokeOpacity={0.9}
                label={{ value: fmtEur(hi.max), position: 'right', fill: UP_COLOR, fontSize: 11, fontWeight: 600 }}
              />
            )}
            {traitFor(lo, 'min') && (
              <ReferenceLine
                segment={traitFor(lo, 'min')} stroke={DOWN_COLOR} strokeWidth={1.5} strokeOpacity={0.9}
                label={{ value: fmtEur(lo.min), position: 'right', fill: DOWN_COLOR, fontSize: 11, fontWeight: 600 }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
})
