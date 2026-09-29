/**
 * PriceDayAheadChart — the last priced day, slot by slot, with the residual
 * load that explains it.
 *
 * Two things this chart insists on:
 *
 * 1. The price is drawn as steps, not a curve. A day-ahead price is a flat
 *    rate for each 15-min market time unit; a smoothed line would invent
 *    prices between slots that were never quoted.
 * 2. The residual load — consumption minus wind and solar — sits behind it on
 *    its own axis. Wind and solar produce what the weather allows rather than
 *    what the market asks for, so only what is left over is actually bid on.
 *    When the residual collapses the price collapses with it, and showing
 *    both makes that the chart's subject rather than a caption.
 */
import { memo, useMemo } from 'react'
import {
  ComposedChart, Area, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ReferenceLine, ResponsiveContainer,
} from 'recharts'

// Teal is the app's accent and is spent on one thing per chart: the series
// the viewer is meant to read. Here that is the price. Everything underneath
// borrows the production tab's palette instead, so a green band means wind
// and an amber one means solar wherever they appear on the dashboard.
const PRICE_COLOR = '#2dd4bf'
const NEG_COLOR = '#ef4444'
const EOLIEN_COLOR = '#10b981'
const SOLAIRE_COLOR = '#f59e0b'

function hhmm(ts) {
  const d = new Date(String(ts).replace(' ', 'T'))
  if (isNaN(d)) return String(ts).slice(11, 16)
  return String(d.getUTCHours()).padStart(2, '0') + ':' + String(d.getUTCMinutes()).padStart(2, '0')
}

function fmtEur(v, digits = 2) {
  return v == null ? '—' : `${v.toFixed(digits).replace('.', ',')} €`
}

function fmtGw(mw) {
  return mw == null ? '—' : `${(mw / 1000).toFixed(1).replace('.', ',')} GW`
}

function fmtDayLong(iso) {
  if (!iso) return ''
  const d = new Date(iso + 'T00:00:00Z')
  if (isNaN(d)) return iso
  return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

function DayAheadTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const r = payload[0].payload
  return (
    <div className="map-tooltip" style={{ position: 'static' }}>
      <strong>{r.t}</strong>
      <span className="map-tooltip__value" style={{ color: r.price < 0 ? NEG_COLOR : PRICE_COLOR }}>
        {fmtEur(r.price)}/MWh
      </span>
      {r.residu != null && (
        <>
          {/* The subtraction written out: the tooltip is where "résidu"
              stops being jargon. */}
          <span style={{ fontSize: '0.75rem' }}>
            {fmtGw(r.cons)} consommés − {fmtGw(r.eolien)} éolien − {fmtGw(r.solaire)} solaire
          </span>
          <span style={{ fontSize: '0.75rem', fontWeight: 600 }}>
            = {fmtGw(r.residu)} à produire autrement
          </span>
        </>
      )}
    </div>
  )
}

/**
 * @param {{
 *   day: string|null,
 *   data: Array<{timestamp:string, price_eur_mwh:number, consommation_mw:number, renouvelable_mw:number, residu_mw:number}>,
 *   loading?: boolean,
 * }} props
 */
export const PriceDayAheadChart = memo(function PriceDayAheadChart({ day, data = [], loading = false }) {
  const { rows, hasResidual } = useMemo(() => {
    const rows_ = data
      .filter(r => r.price_eur_mwh != null)
      .map(r => ({
        t: hhmm(r.timestamp),
        price: r.price_eur_mwh,
        residu: r.residu_mw,
        cons: r.consommation_mw,
        ren: r.renouvelable_mw,
        eolien: r.eolien_mw,
        solaire: r.solaire_mw,
      }))
    // residu + éolien + solaire stack to exactly consommation, so the chart
    // shows the subtraction as three slabs instead of asserting it in a
    // caption.
    return { rows: rows_, hasResidual: rows_.some(r => r.residu != null) }
  }, [data])

  const title = 'Prix day-ahead & résidu de charge'
  const explain = "Prix spot day-ahead publié la veille pour cette journée, créneau de 15 min par créneau de 15 min. En fond, le résidu de charge : la consommation moins l'éolien et le solaire, c'est-à-dire la part de la demande qui reste à couvrir avec des moyens pilotables — et donc la seule part qui se négocie."

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="day-ahead-loading">
        <h2 className="chart-title">{title}</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="glass-card chart-card" data-testid="day-ahead-empty">
        <h2 className="chart-title">{title}</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune journée cotée disponible</p></div>
      </section>
    )
  }

  const lo = rows.reduce((a, b) => (b.price < a.price ? b : a))
  const hi = rows.reduce((a, b) => (b.price > a.price ? b : a))
  const trough = hasResidual
    ? rows.filter(r => r.residu != null).reduce((a, b) => (b.residu < a.residu ? b : a))
    : null

  return (
    <section className="glass-card chart-card" data-testid="day-ahead">
      <div className="price-hero__head">
        <h2 className="chart-title" title={explain}>{title}</h2>
        <span className="price-profile__note">
          {fmtDayLong(day)} · {rows.length} créneaux
        </span>
      </div>

      <div style={{ flex: '1 1 0', minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <defs>
              {/* Fades to nothing at the baseline: the slab shows the shape of
                  the residual, it doesn't claim the whole area beneath it. */}
              <linearGradient id="residu-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor="var(--color-text-muted)" stopOpacity={0.34} />
                <stop offset="100%" stopColor="var(--color-text-muted)" stopOpacity={0} />
              </linearGradient>
              {/* One gradient per source rather than one blended band: the
                  production tab's green is wind and its amber is solar, and
                  fading one into the other would invent a colour that means
                  neither. */}
              <linearGradient id="eolien-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={EOLIEN_COLOR} stopOpacity={0.5} />
                <stop offset="100%" stopColor={EOLIEN_COLOR} stopOpacity={0.22} />
              </linearGradient>
              <linearGradient id="solaire-grad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%"   stopColor={SOLAIRE_COLOR} stopOpacity={0.5} />
                <stop offset="100%" stopColor={SOLAIRE_COLOR} stopOpacity={0.22} />
              </linearGradient>
            </defs>

            <CartesianGrid strokeDasharray="3 3" stroke="#888" strokeOpacity={0.15} vertical={false} />
            <XAxis
              dataKey="t" interval={11} tickLine={false}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 10 }}
            />
            <YAxis
              yAxisId="price" tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              unit=" €" width={52} tickLine={false}
            />
            <YAxis
              yAxisId="load" orientation="right" hide={!hasResidual}
              tick={{ fill: 'var(--color-text-muted)', fontSize: 11 }}
              width={48} tickLine={false}
              tickFormatter={v => `${Math.round(v / 1000)} GW`}
            />
            <Tooltip content={<DayAheadTooltip />} cursor={{ stroke: 'var(--color-text)', strokeOpacity: 0.25 }} />

            {hasResidual && (
              <>
                {/* Stacked, so the top of the band is consommation and the
                    coloured slab is literally what wind and solar took out
                    of it. */}
                <Area
                  yAxisId="load" type="monotone" dataKey="residu" stackId="load"
                  stroke="var(--color-text-muted)" strokeWidth={1.2} strokeOpacity={0.8}
                  fill="url(#residu-grad)" isAnimationActive={false} connectNulls
                />
                <Area
                  yAxisId="load" type="monotone" dataKey="eolien" stackId="load"
                  stroke={EOLIEN_COLOR} strokeWidth={1} strokeOpacity={0.8}
                  fill="url(#eolien-grad)" isAnimationActive={false} connectNulls
                />
                <Area
                  yAxisId="load" type="monotone" dataKey="solaire" stackId="load"
                  stroke={SOLAIRE_COLOR} strokeWidth={1} strokeOpacity={0.8}
                  fill="url(#solaire-grad)" isAnimationActive={false} connectNulls
                />
              </>
            )}

            <ReferenceLine yAxisId="price" y={0} stroke={NEG_COLOR} strokeDasharray="4 4" strokeOpacity={0.6} />
            <Line
              yAxisId="price" type="stepAfter" dataKey="price" dot={false}
              stroke={PRICE_COLOR} strokeWidth={2.2} isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="price-dayahead__gloss">
        {hasResidual && (
          <span className="price-legend">
            <span className="price-legend__item">
              <i className="price-legend__line" style={{ background: PRICE_COLOR }} />prix spot
            </span>
            <span className="price-legend__item">
              <i className="price-legend__box" style={{ background: 'rgba(16,185,129,0.5)' }} />éolien
            </span>
            <span className="price-legend__item">
              <i className="price-legend__box" style={{ background: 'rgba(245,158,11,0.5)' }} />solaire
            </span>
            <span className="price-legend__item">
              <i className="price-legend__box price-legend__box--residu" />résidu de charge
            </span>
            <span className="price-legend__note">les trois empilés = consommation</span>
          </span>
        )}
        <span>
          {trough && (
            <>Résidu au plus bas à <strong>{trough.t}</strong> : {fmtGw(trough.residu)} sur {fmtGw(trough.cons)} consommés, prix {fmtEur(trough.price)}. </>
          )}
          Plus haut du jour {fmtEur(hi.price)} à {hi.t}, plus bas {fmtEur(lo.price)} à {lo.t}.
        </span>
      </div>
    </section>
  )
})
