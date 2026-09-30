/**
 * PriceDayAheadChart — the last priced day, with two optional context layers.
 *
 * Hand-rolled SVG rather than recharts. Two reasons: the historical layer
 * draws one polyline per day of the archive, which recharts has no sensible
 * way to express; and the axes have to stay frozen across layer changes, so
 * the line never shifts when the background does.
 *
 * Three choices worth keeping:
 *
 * 1. The price is drawn in steps. A day-ahead price is a flat rate for each
 *    15-min market time unit — a smooth curve would show prices that were
 *    never quoted. The background days are smoothed instead: at ~150 of them
 *    superposed, steps produce a moiré that eats the whole plot.
 * 2. The y axis is fixed at 1.5x the day's own high, and asymmetric (the
 *    bottom gets two thirds of the top). Outliers in the archive are clipped
 *    rather than allowed to squash the day — their amplitude is readable in
 *    the history bars, not here.
 * 3. Only wind and solar come off demand. They produce whatever the weather
 *    allows; hydro stores and picks its moment, so it bids into the market
 *    instead of being subtracted from the load.
 */
import { memo, useMemo, useRef, useState } from 'react'

const W = 900
// Rapport calé sur celui de la colonne : plus large, le tracé laissait des
// bandes vides en haut et en bas de sa carte.
const H = 660
const PAD = { t: 18, r: 46, b: 34, l: 44 }

/** Minutes since midnight, in the UTC frame every chart here plots in. */
function minsOf(ts) {
  const d = new Date(String(ts).replace(' ', 'T'))
  if (isNaN(d)) return 0
  return d.getUTCHours() * 60 + d.getUTCMinutes()
}

function hhmm(ts) {
  const m = minsOf(ts)
  return `${String(Math.floor(m / 60)).padStart(2, '0')}:${String(m % 60).padStart(2, '0')}`
}

const fmtEur = (v, d = 2) => (v == null ? '—' : `${v.toFixed(d).replace('.', ',')} €`)
const fmtGw = mw => (mw == null ? '—' : `${(mw / 1000).toFixed(1).replace('.', ',')} GW`)

function fmtDayShort(iso) {
  const d = new Date(`${iso}T00:00:00Z`)
  if (isNaN(d)) return iso
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', timeZone: 'UTC' })
}

function fmtDayLong(iso) {
  if (!iso) return ''
  const d = new Date(`${iso}T00:00:00Z`)
  if (isNaN(d)) return iso
  return d.toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'UTC' })
}

function quantile(sorted, p) {
  const i = (sorted.length - 1) * p
  const lo = Math.floor(i)
  const hi = Math.ceil(i)
  return lo === hi ? sorted[lo] : sorted[lo] + (sorted[hi] - sorted[lo]) * (i - lo)
}

/** One polyline per day of the archive, plus per-slot quantiles for the tooltip. */
function buildContext(history) {
  const byDay = new Map()
  const bySlot = new Map()
  for (const r of history) {
    const v = r.price_eur_mwh
    if (v == null) continue
    const day = String(r.timestamp).slice(0, 10)
    const m = minsOf(r.timestamp)
    if (!byDay.has(day)) byDay.set(day, [])
    byDay.get(day).push([m, v])
    if (!bySlot.has(m)) bySlot.set(m, [])
    bySlot.get(m).push(v)
  }
  const days = []
  const kept = []
  for (const [d, pts] of byDay) {
    // Partial days would draw a truncated line across the plot.
    if (pts.length <= 76) continue
    pts.sort((a, b) => a[0] - b[0])
    days.push(pts)
    kept.push(d)
  }
  kept.sort()
  const slots = new Map()
  for (const [m, vals] of bySlot) {
    const s = [...vals].sort((a, b) => a - b)
    slots.set(m, { p10: quantile(s, 0.1), p50: quantile(s, 0.5), p90: quantile(s, 0.9) })
  }
  return { days, slots, span: kept.length ? { from: kept[0], to: kept[kept.length - 1] } : null }
}

const LAYERS = [
  { id: 'charge', label: 'Le résidu de charge', swatch: 'price-tog__sw--load' },
  { id: 'histo', label: 'Les prix observés', swatch: 'price-tog__sw--hist' },
]

const HINT_COMMON =
  "La journée cotée est tracée en marches : un prix day-ahead est un tarif fixe sur chaque créneau " +
  "de 15 minutes, pas une grandeur continue. Les journées de fond sont lissées — à une centaine " +
  "superposées, le palier devient illisible."

const HINTS = {
  none:
    "Le prix spot de la dernière journée cotée, créneau par créneau. Les deux boutons ajoutent au " +
    "choix une couche de contexte : pourquoi ce prix, ou s'il est normal. " + HINT_COMMON,
  charge:
    "La courbe claire est le résidu de charge, sur l'axe droit en GW : la demande une fois retirée " +
    "la production éolienne et solaire. Le coin coloré au-dessus est précisément ce que la météo a " +
    "retiré. Seul le résidu se négocie sur le marché, et c'est pour cela qu'il monte et descend " +
    "avec le prix. " + HINT_COMMON,
  histo: null,   // dépend des données : construit par hintHisto()
}

/**
 * Le libellé « prix observés » doit dire de quoi il est fait : combien de
 * journées, et sur quelle fenêtre. Sans ça, rien ne distingue un relevé d'une
 * norme calculée.
 */
function hintHisto(days, span) {
  const window = span ? ` — du ${span.from} au ${span.to}` : ''
  return (
    `Chaque trait pâle est une journée réellement cotée, tracée sur le même axe de 24 h : ` +
    `les ${days} journées complètes les plus récentes de l'historique${window}. ` +
    `Ce sont des relevés, pas une moyenne — la dispersion est montrée telle quelle, et la ` +
    `position de la journée cotée dans le peloton se lit directement. ` + HINT_COMMON
  )
}

/**
 * @param {{
 *   day: string|null,
 *   data: Array<Object>,
 *   history: Array<{timestamp:string, price_eur_mwh:number}>,
 *   loading?: boolean,
 * }} props
 */
export const PriceDayAheadChart = memo(function PriceDayAheadChart({
  day, data = [], history = [], loading = false,
}) {
  const [layer, setLayer] = useState('none')
  const [hover, setHover] = useState(null)
  const svgRef = useRef(null)

  const rows = useMemo(
    () => data.filter(r => r.price_eur_mwh != null).map(r => ({ ...r, m: minsOf(r.timestamp) })),
    [data],
  )
  // Built once for the whole archive — toggling a layer must not pay for it.
  const context = useMemo(() => buildContext(history), [history])

  const geom = useMemo(() => {
    if (!rows.length) return null
    const prices = rows.map(r => r.price_eur_mwh)
    const pMax = Math.max(...prices) * 1.5
    const pMin = -pMax * (2 / 3)
    const lMax = Math.max(...rows.map(r => r.consommation_mw || 0)) * 1.12 || 1
    const x = m => PAD.l + (m / 1440) * (W - PAD.l - PAD.r)
    const yP = v => PAD.t + (1 - (v - pMin) / (pMax - pMin)) * (H - PAD.t - PAD.b)
    // Load reads in the same upper half as positive prices, off a shared zero.
    const yL = v => yP(0) - (v / lMax) * (yP(0) - yP(pMax))
    const step = pMax > 400 ? 200 : (pMax > 200 ? 100 : 50)
    const ticks = []
    for (let t = -Math.floor(pMax / step) * step; t <= pMax; t += step) ticks.push(t)
    return { pMax, pMin, lMax, x, yP, yL, ticks }
  }, [rows])

  if (loading) {
    return (
      <section className="glass-card chart-card price-hero" data-testid="day-ahead-loading">
        <h2 className="chart-title">Prix day-ahead — France</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!rows.length || !geom) {
    return (
      <section className="glass-card chart-card price-hero" data-testid="day-ahead-empty">
        <h2 className="chart-title">Prix day-ahead — France</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune journée cotée disponible</p></div>
      </section>
    )
  }

  const { x, yP, yL, lMax, pMax, pMin, ticks } = geom
  const spanLabel = context.span && {
    from: fmtDayShort(context.span.from),
    to: fmtDayShort(context.span.to),
  }
  const last = rows[rows.length - 1]
  const hi = rows.reduce((a, b) => (b.price_eur_mwh > a.price_eur_mwh ? b : a))
  const lo = rows.reduce((a, b) => (b.price_eur_mwh < a.price_eur_mwh ? b : a))
  const withResidu = rows.filter(r => r.residu_mw != null)
  const trough = withResidu.length
    ? withResidu.reduce((a, b) => (b.residu_mw < a.residu_mw ? b : a))
    : null
  const above = rows.filter(r => {
    const q = context.slots.get(r.m)
    return q && r.price_eur_mwh > q.p90
  }).length

  const pricePath = rows
    .map((r, i) => {
      const y = yP(r.price_eur_mwh)
      return `${i ? 'L' : 'M'}${x(r.m)} ${y}L${x(Math.min(1440, r.m + 15))} ${y}`
    })
    .join('')

  const stackPath = (low, high) => {
    let d = rows.map((r, i) => `${i ? 'L' : 'M'}${x(r.m)} ${yL(high(r))}`).join('')
    for (let i = rows.length - 1; i >= 0; i--) d += `L${x(rows[i].m)} ${yL(low(rows[i]))}`
    return `${d}Z`
  }
  const fResid = r => r.residu_mw || 0
  const fEol = r => (r.residu_mw || 0) + (r.eolien_mw || 0)
  const fAll = r => (r.residu_mw || 0) + (r.eolien_mw || 0) + (r.solaire_mw || 0)

  function onMove(e) {
    const box = svgRef.current.getBoundingClientRect()
    const px = ((e.clientX - box.left) / box.width) * W
    const m = Math.max(0, Math.min(1440, ((px - PAD.l) / (W - PAD.l - PAD.r)) * 1440))
    let best = rows[0]
    let bd = Infinity
    for (const r of rows) {
      const d = Math.abs(r.m - m)
      if (d < bd) { bd = d; best = r }
    }
    setHover({ row: best, cx: e.clientX, cy: e.clientY })
  }

  const hq = hover && context.slots.get(hover.row.m)

  return (
    <section className="glass-card chart-card price-hero" data-testid="day-ahead">
      <div className="price-hero__head">
        <div>
          <p className="price-hero__kicker">La journée cotée</p>
          <h2 className="chart-title">
            Prix day-ahead — France
            <button type="button" className="hint" aria-label="Comment lire ce graphique">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"
                   strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M9 18h6M10 22h4" />
                <path d="M12 2a7 7 0 0 0-4 12.7V18h8v-3.3A7 7 0 0 0 12 2Z" />
              </svg>
              <span className="hint__body">
                {layer === 'histo'
                  ? hintHisto(context.days.length, spanLabel)
                  : HINTS[layer]}
              </span>
            </button>
          </h2>
        </div>
        <div className="price-hero__right">
          <span className="price-hero__meta">{fmtDayLong(day)} · {rows.length} créneaux</span>
          {/* Toggles rather than a single-choice selector: clicking the active
              layer removes it, which a radio group cannot express. */}
          <div className="price-tog" aria-label="Couches du graphique">
            {LAYERS.map(l => {
              const on = layer === l.id
              return (
                <button
                  key={l.id} type="button" className="price-tog__b" aria-pressed={on}
                  title={`${on ? 'Retirer' : 'Ajouter'} ${l.label.toLowerCase()} ${on ? 'du' : 'au'} graphique`}
                  onClick={() => setLayer(on ? 'none' : l.id)}
                >
                  <i className="price-tog__sign" aria-hidden="true" />
                  <i className={`price-tog__sw ${l.swatch}`} aria-hidden="true" />
                  {l.label}
                </button>
              )
            })}
          </div>
        </div>
      </div>

      <div className="price-hero__plot">
        <svg
          ref={svgRef} viewBox={`0 0 ${W} ${H}`} className="price-hero__svg" role="img"
          aria-label="Prix spot day-ahead de la dernière journée cotée"
        >
          <defs>
            <clipPath id="da-clip">
              <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={H - PAD.t - PAD.b} />
            </clipPath>
          </defs>

          {ticks.filter(v => v >= pMin && v <= pMax).map(v => (
            <g key={v}>
              <line
                x1={PAD.l} x2={W - PAD.r} y1={yP(v)} y2={yP(v)}
                className={v === 0 ? 'price-zeroline' : 'price-gridline'}
              />
              <text x={PAD.l - 8} y={yP(v) + 4} textAnchor="end" className="price-ax">{v} €</text>
            </g>
          ))}
          {Array.from({ length: Math.floor(lMax / 15000) }, (_, i) => (i + 1) * 15000).map(g => (
            <text key={g} x={W - PAD.r + 7} y={yL(g) + 4} className="price-ax">{g / 1000} GW</text>
          ))}
          {[0, 3, 6, 9, 12, 15, 18, 21].map(h => (
            <text
              key={h} x={x(h * 60)} y={H - PAD.b + 18} className="price-ax"
              textAnchor={h === 0 ? 'start' : 'middle'}
            >
              {String(h).padStart(2, '0')}:00
            </text>
          ))}

          <g clipPath="url(#da-clip)" className={`price-plot is-${layer}`}>
            {context.days.map((pts, i) => (
              <path
                key={i} className="price-ghostday"
                d={pts.map((p, j) => `${j ? 'L' : 'M'}${x(p[0])} ${yP(p[1])}`).join('')}
              />
            ))}
            <path className="price-wedge price-wedge--residu" d={stackPath(() => 0, fResid)} />
            <path className="price-wedge price-wedge--eolien" d={stackPath(fResid, fEol)} />
            <path className="price-wedge price-wedge--solaire" d={stackPath(fEol, fAll)} />
            <path
              className="price-residline"
              d={rows.map((r, i) => `${i ? 'L' : 'M'}${x(r.m)} ${yL(fResid(r))}`).join('')}
            />
            <path className="price-line" d={pricePath} />
          </g>

          {hover && (
            <line
              x1={x(hover.row.m)} x2={x(hover.row.m)} y1={PAD.t} y2={H - PAD.b}
              className="price-annotline"
            />
          )}
          <circle
            cx={x(Math.min(1440, last.m + 15))} cy={yP(last.price_eur_mwh)}
            r={3.5} className="price-end"
          />
          <text
            x={x(Math.min(1440, last.m + 15)) + 7} y={yP(last.price_eur_mwh) + 4}
            className="price-end__label"
          >
            {fmtEur(last.price_eur_mwh, 0)}
          </text>

          <rect
            x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={H - PAD.t - PAD.b}
            fill="transparent" onPointerMove={onMove} onPointerLeave={() => setHover(null)}
          />
        </svg>

        {hover && (
          <div
            className="map-tooltip price-tip"
            style={{
              position: 'fixed',
              left: Math.min(window.innerWidth - 300, hover.cx + 14),
              top: Math.max(8, hover.cy - 90),
            }}
          >
            <strong>{hhmm(hover.row.timestamp)}</strong>
            <span className="map-tooltip__value">{fmtEur(hover.row.price_eur_mwh)}/MWh</span>
            {hover.row.residu_mw != null && (
              <>
                <span className="price-tip__h">Ce qui l&apos;explique</span>
                <span className="price-tip__s">
                  {fmtGw(hover.row.consommation_mw)} consommés − {fmtGw(hover.row.eolien_mw)} éolien
                  {' '}− {fmtGw(hover.row.solaire_mw)} solaire
                </span>
                <span className="price-tip__s">
                  <strong>= {fmtGw(hover.row.residu_mw)} à produire autrement</strong>
                </span>
              </>
            )}
            {hq && (
              <>
                <span className="price-tip__h">Face aux autres journées</span>
                <span className="price-tip__s">
                  habituel {fmtEur(hq.p50, 0)}, 8 jours sur 10 entre {fmtEur(hq.p10, 0)} et {fmtEur(hq.p90, 0)}
                </span>
                <span className="price-tip__s">
                  <strong>
                    {hover.row.price_eur_mwh > hq.p90
                      ? 'au-dessus des 9 journées sur 10'
                      : (hover.row.price_eur_mwh < hq.p10 ? 'en dessous des 9 journées sur 10' : 'dans la normale')}
                  </strong>
                </span>
              </>
            )}
          </div>
        )}
      </div>

      <div className="price-legend">
        <span className="price-legend__i">
          <i className="price-legend__line" style={{ background: 'var(--color-accent)' }} />
          <strong>la journée cotée</strong> — axe gauche
        </span>
        <span className="price-legend__i">
          <i className="price-legend__line price-legend__line--resid" />
          <strong>résidu</strong> — axe droit, en GW
        </span>
        <span className="price-legend__i">
          <i className="price-legend__box" style={{ background: 'var(--color-eolien)', opacity: 0.5 }} />éolien
        </span>
        <span className="price-legend__i">
          <i className="price-legend__box" style={{ background: 'var(--color-solaire)', opacity: 0.5 }} />solaire
        </span>
        <span className="price-legend__sep" />
        <span className="price-legend__i">
          <i className="price-legend__line price-legend__line--ghost" />
          les {context.days.length} autres journées
        </span>
      </div>

      <p className="price-hero__gloss">
        {trough && (
          <>
            Résidu au plus bas à <strong>{hhmm(trough.timestamp)}</strong> ({fmtGw(trough.residu_mw)} sur
            {' '}{fmtGw(trough.consommation_mw)} consommés) ·{' '}
          </>
        )}
        <strong>{above}</strong> créneaux sur {rows.length} plus chers que 9 journées sur 10 ·
        {' '}plus haut {fmtEur(hi.price_eur_mwh)} à {hhmm(hi.timestamp)},
        {' '}plus bas {fmtEur(lo.price_eur_mwh)} à {hhmm(lo.timestamp)}.
      </p>
    </section>
  )
})
