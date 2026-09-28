/**
 * PriceHourlyProfile — average spot price by hour of day, over the whole
 * available history.
 *
 * The companion to PriceHistoryBars: the bars say *when* prices went
 * negative, this says *at what time of day* they do it. Three months of
 * 15-min data collapsed onto a single 24 h axis draws the duck curve
 * directly — the midday solar trough and the evening ramp — with the
 * usual spread (p10–p90) shown as a band behind the mean line.
 */
import { memo, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'

const LINE_COLOR = '#2dd4bf'
const NEG_COLOR = '#ef4444'

function hourOf(ts) {
  const d = new Date(String(ts).replace(' ', 'T'))
  if (isNaN(d)) return null
  return d.getUTCHours()
}

function fmtEur(v, digits = 2) {
  return v == null ? '—' : `${v.toFixed(digits).replace('.', ',')} €`
}

/** Value at a percentile of an already-sorted array. */
function quantile(sorted, q) {
  const i = (sorted.length - 1) * q
  const lo = Math.floor(i)
  const hi = Math.ceil(i)
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo)
}

/** Collapse the series onto 24 hour-of-day buckets. */
function buildHourlyRows(data) {
  const buckets = Array.from({ length: 24 }, () => [])
  for (const r of data) {
    const v = r.price_eur_mwh
    if (v == null) continue
    const h = hourOf(r.timestamp)
    if (h == null) continue
    buckets[h].push(v)
  }
  return buckets
    .map((vals, h) => {
      if (!vals.length) return null
      const sorted = [...vals].sort((a, b) => a - b)
      // The band is p10–p90, not min–max: a single -500 EUR afternoon would
      // otherwise stretch the band over the whole plot and flatten the mean
      // line this chart exists to show.
      const p10 = quantile(sorted, 0.1)
      const p90 = quantile(sorted, 0.9)
      return {
        hour: h,
        label: `${String(h).padStart(2, '0')}h`,
        mean: vals.reduce((a, b) => a + b, 0) / vals.length,
        p10,
        p90,
        min: sorted[0],
        max: sorted[sorted.length - 1],
        // Plotted as a stacked pair so the band spans p10..p90 without a
        // dedicated range mark: an invisible base, then the spread above it.
        base: p10,
        spread: p90 - p10,
        negPct: Math.round((100 * vals.filter(v => v < 0).length) / vals.length),
      }
    })
    .filter(Boolean)
}

function ProfileTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="map-tooltip" style={{ position: 'static' }}>
      <strong>{row.label} — {String((row.hour + 1) % 24).padStart(2, '0')}h</strong>
      <span className="map-tooltip__value">moyenne {fmtEur(row.mean)}/MWh</span>
      <span style={{ fontSize: '0.75rem' }}>
        8 fois sur 10 entre {fmtEur(row.p10)} et {fmtEur(row.p90)}
      </span>
      <span style={{ fontSize: '0.72rem', color: '#a1a1aa' }}>
        extrêmes {fmtEur(row.min)} / {fmtEur(row.max)}
      </span>
      {row.negPct > 0 && (
        <span style={{ fontSize: '0.75rem', color: NEG_COLOR }}>
          {row.negPct} % des créneaux sous 0 €
        </span>
      )}
    </div>
  )
}

/** @param {{ data: Array<{timestamp:string, price_eur_mwh:number}>, loading?: boolean }} props */
export const PriceHourlyProfile = memo(function PriceHourlyProfile({ data = [], loading = false }) {
  const rows = useMemo(() => buildHourlyRows(data), [data])

  const title = 'Profil horaire moyen'
  const explain = "Prix spot moyen pour chaque heure de la journée, sur tout l'historique disponible. La bande montre l'écart entre le plus bas et le plus haut observés à cette heure-là."

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="price-profile-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="glass-card chart-card" data-testid="price-profile-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  const cheapest = rows.reduce((a, b) => (b.mean < a.mean ? b : a))
  const dearest  = rows.reduce((a, b) => (b.mean > a.mean ? b : a))

  return (
    <section className="glass-card chart-card" data-testid="price-profile">
      <div className="price-hero__head">
        <h2 className="chart-title" title={explain}>{title}</h2>
        <span className="price-profile__note">
          creux {cheapest.label} · pic {dearest.label} · bande p10–p90
        </span>
      </div>

      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} vertical={false} />
            <XAxis
              dataKey="label" interval={2} tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            />
            <YAxis tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }} unit=" €" width={52} tickLine={false} />
            <Tooltip content={<ProfileTooltip />} cursor={{ stroke: 'var(--color-text)', strokeOpacity: 0.25 }} />

            <Area dataKey="base"   stackId="band" stroke="none" fill="none" isAnimationActive={false} />
            <Area dataKey="spread" stackId="band" stroke="none" fill={LINE_COLOR} fillOpacity={0.12} isAnimationActive={false} />

            <ReferenceLine y={0} stroke={NEG_COLOR} strokeDasharray="4 4" strokeOpacity={0.6} />
            <Line
              type="monotone" dataKey="mean" dot={false} isAnimationActive={false}
              stroke={LINE_COLOR} strokeWidth={2}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
})
