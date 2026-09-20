/**
 * FranceMap — choropleth map of the 13 French metropolitan regions.
 *
 * Modes recolor + relabel the same map rather than switching components,
 * so it stays visually anchored in the same spot across every dashboard tab.
 * Clicking a region triggers onSelect(code_insee) for drill-down.
 *
 * Production-unit pins used to live here (fetched per selected region) —
 * moved out entirely: showing installations on every tab's map was noise,
 * they now only appear once, on the dedicated MaintenanceMap.
 *
 * No "part renouvelable par région" mode: a region's production isn't a fair
 * proxy for how green that region *is* — large plants (nuclear especially)
 * serve the national grid, not their host region, so a region simply
 * hosting few power plants would read as a false "100% renewable" — that's
 * an artifact of where RTE meters production, not a real regional signal.
 *
 * "load" mode (consumption vs each region's own installed capacity) is a
 * different, legitimate use of the same nuclear-siting fact: it doesn't
 * claim a region "is" anything, it just shows *why* a region's capacity is
 * what it is — the nuclear pins are context for the choropleth, not a
 * metric of their own.
 *
 * "curtailment" mode — the app's actual point: which regions drive
 * curtailment, i.e. hold the largest share of national wind+solar surplus
 * during negative-price windows (see api/curtailment_service.py). Nuclear
 * and hydro are excluded from the underlying surplus calc for the same
 * reason "load" mode's nuclear pins exist — raw production share would
 * just re-rank the same nuclear-heavy regions regardless of curtailment.
 *
 * showMixRibbon adds a thin, muted mix ribbon beside the map — independent
 * of `mode`, since it's a secondary/background read (current selection's
 * source breakdown), not another choropleth. Clicking a wedge highlights
 * that source's regional production as proportional circles on the map
 * itself — per region, not per plant: there's no live per-plant output in
 * this pipeline, only per-region-per-source aggregates (regionSources).
 */
import { memo, useState, useEffect, useMemo } from 'react'
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps'
import { geoCentroid } from 'd3-geo'
import { fetchProductionUnits } from '../services/api.js'

const GEO_URL = '/france-regions.geojson'

export const SOURCE_ORDER = ['nucleaire', 'eolien', 'solaire', 'hydraulique', 'bioenergies', 'thermique']
export const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  bioenergies: '#84cc16',
  thermique:   '#ef4444',
}
export const SOURCE_LABELS = {
  nucleaire:   'Nucléaire',
  eolien:      'Éolien',
  solaire:     'Solaire',
  hydraulique: 'Hydraulique',
  bioenergies: 'Bioénergies',
  thermique:   'Thermique fossile',
}

const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2200 }

// ── Mix ribbon (thin quarter-donut, radial dividers by construction) ──────
const ARC_START = 270  // 9 o'clock
const ARC_END   = 360  // 12 o'clock
const RIBBON_R_OUTER = 92
const RIBBON_R_INNER = 78

/** Muted version of a source color — mixed toward the card background so
 * the ribbon reads as a background element, not competing with whatever
 * the map itself is showing. */
function mutedSourceColor(hex) {
  const h = hex.replace('#', '')
  const [r, g, b] = [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16))
  const bg = [23, 21, 18] // ~ var(--color-surface-1)
  const t = 0.55
  return `rgb(${Math.round(r * t + bg[0] * (1 - t))}, ${Math.round(g * t + bg[1] * (1 - t))}, ${Math.round(b * t + bg[2] * (1 - t))})`
}

function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = ((angleDeg % 360) - 90) * Math.PI / 180
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) }
}

function annularSegmentPath(cx, cy, rInner, rOuter, startAngle, endAngle) {
  if (endAngle - startAngle >= 359.999) endAngle = startAngle + 359.999
  const p1 = polarToCartesian(cx, cy, rOuter, endAngle)
  const p2 = polarToCartesian(cx, cy, rOuter, startAngle)
  const p3 = polarToCartesian(cx, cy, rInner, startAngle)
  const p4 = polarToCartesian(cx, cy, rInner, endAngle)
  const largeArc = endAngle - startAngle > 180 ? 1 : 0
  return [
    `M ${p1.x} ${p1.y}`,
    `A ${rOuter} ${rOuter} 0 ${largeArc} 0 ${p2.x} ${p2.y}`,
    `L ${p3.x} ${p3.y}`,
    `A ${rInner} ${rInner} 0 ${largeArc} 1 ${p4.x} ${p4.y}`,
    'Z',
  ].join(' ')
}

/** Outline of the whole combined ring (outer arc + one end + inner arc +
 * other end) as a single stroked path — one border around the shape, not
 * one per wedge, so the radial cuts between sources don't read as seams. */
function ringOutlinePath(cx, cy, rInner, rOuter, startAngle, endAngle) {
  const oStart = polarToCartesian(cx, cy, rOuter, startAngle)
  const oEnd   = polarToCartesian(cx, cy, rOuter, endAngle)
  const iEnd   = polarToCartesian(cx, cy, rInner, endAngle)
  const iStart = polarToCartesian(cx, cy, rInner, startAngle)
  const largeArc = endAngle - startAngle > 180 ? 1 : 0
  return [
    `M ${oStart.x} ${oStart.y}`,
    `A ${rOuter} ${rOuter} 0 ${largeArc} 1 ${oEnd.x} ${oEnd.y}`,
    `L ${iEnd.x} ${iEnd.y}`,
    `A ${rInner} ${rInner} 0 ${largeArc} 0 ${iStart.x} ${iStart.y}`,
    'Z',
  ].join(' ')
}

const LOW_COLOR  = [24, 45, 44]     // dim, desaturated teal
const HIGH_COLOR = [45, 212, 191]   // #2dd4bf — accent teal
const LOAD_LOW   = [20, 26, 40]     // dim, desaturated blue — calm, not alarmist
const LOAD_HIGH  = [59, 130, 246]   // #3b82f6
const CURTAIL_LOW  = [40, 30, 16]   // dim, desaturated amber
const CURTAIL_HIGH = [245, 158, 11] // #f59e0b

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

/** Interpolate a teal intensity from production volume relative to the region max. */
function volumeColor(prod, maxProd) {
  const t = maxProd > 0 ? Math.min(1, Math.max(0, prod / maxProd)) : 0
  const [r, g, b] = LOW_COLOR.map((c, i) => lerp(c, HIGH_COLOR[i], t))
  return `rgb(${r}, ${g}, ${b})`
}

/** Interpolate a blue intensity from consumption-vs-capacity load relative to the region max. */
function loadColor(pct, maxPct) {
  if (pct == null) return '#1c2538'
  const t = maxPct > 0 ? Math.min(1, Math.max(0, pct / maxPct)) : 0
  const [r, g, b] = LOAD_LOW.map((c, i) => lerp(c, LOAD_HIGH[i], t))
  return `rgb(${r}, ${g}, ${b})`
}

/** Interpolate an amber intensity from a region's share of national
 * curtailment-driving wind+solar surplus (0-100%, already normalized). */
function curtailmentColor(pct) {
  if (pct == null) return '#1c2538'
  const t = Math.min(1, Math.max(0, pct / 100))
  const [r, g, b] = CURTAIL_LOW.map((c, i) => lerp(c, CURTAIL_HIGH[i], t))
  return `rgb(${r}, ${g}, ${b})`
}

/** Same 4 thresholds as the national carbon badge — green<100, lime<250, amber<400, red>=400. */
function carbonColor(intensity) {
  if (intensity == null) return '#1c2538'
  if (intensity < 100) return '#10b981'
  if (intensity < 250) return '#84cc16'
  if (intensity < 400) return '#f59e0b'
  return '#ef4444'
}

// Diverging color for "export" mode: how far a region's own production sits
// above (teal, structural exporter) or below (amber, structural importer)
// its own consumption — not a claim about physical flow direction, French
// regions share one grid, but a legible proxy for "who's a net contributor".
function balanceColor(ratio) {
  if (ratio == null) return '#1c2538'
  const t = Math.max(-1, Math.min(1, ratio / 2))  // ±200% saturates the scale
  if (t >= 0) {
    const [r, g, b] = [24, 45, 44].map((c, i) => lerp(c, [45, 212, 191][i], t))
    return `rgb(${r}, ${g}, ${b})`
  }
  const [r, g, b] = [45, 40, 24].map((c, i) => lerp(c, [245, 158, 11][i], -t))
  return `rgb(${r}, ${g}, ${b})`
}

const MODE_LABELS = {
  volume:  'Production par région',
  carbon:  'Intensité carbone par région',
  share:   'Part de la production nationale',
  balance: 'Régions exportatrices / importatrices',
  load:    'Consommation vs capacité installée',
  curtailment: 'Risque de curtailment par région',
}

/** Per-source spans (start/end cumulative fraction + %) in fixed order —
 * shared by the ribbon (angular spans) and the per-region strip (length
 * spans along the boundary). */
function mixSpans(sources) {
  const total = Object.values(sources || {}).reduce((s, v) => s + (v > 0 ? v : 0), 0)
  if (total <= 0) return []
  let cursor = 0
  const out = []
  for (const key of SOURCE_ORDER) {
    const mw = sources[key] > 0 ? sources[key] : 0
    if (mw <= 0) continue
    const frac = mw / total
    out.push({ key, pct: frac * 100, start: cursor, end: cursor + frac })
    cursor += frac
  }
  return out
}

/**
 * @param {{
 *   regions: Array<{code_insee:string, region:string}>,
 *   regionTotals: Object,       // { [code_insee]: totalMW }
 *   regionConsommation: Object, // { [code_insee]: consoMW }
 *   selectedCode: string,
 *   onSelect: Function,
 *   loading?: boolean,
 * }} props
 */
export const FranceMap = memo(function FranceMap({
  regions = [],
  regionTotals = {},
  regionConsommation = {},
  regionCarbon = {},   // { [code_insee]: gCO2/kWh } — used when mode="carbon"
  regionLoad = {},      // { [code_insee]: pct } consommation/capacité installée — used when mode="load"
  regionCurtailmentRisk = {}, // { [code_insee]: pct } part du surplus EnR national — used when mode="curtailment"
  regionSources = {},   // { [code_insee]: { nucleaire, eolien, ... } } — per-region breakdown, for the ribbon's click-to-filter circles
  mixSources = null,    // current mix (region if selected, else national) — draws the ribbon
  showMixRibbon = false, // render the thin mix ribbon beside the map — independent of `mode`
  selectedCode,
  onSelect,
  loading = false,
  mode = 'volume',       // 'volume' | 'carbon' | 'share' | 'balance' | 'load' | 'curtailment'
  onModeChange = null,   // (mode) => void — omit to hide the toggle
  availableModes = ['volume', 'carbon', 'share'],
  showNuclearPlants = false,  // overlay geolocated nuclear plants as context pins
}) {
  const [hovered, setHovered] = useState(null)   // { name, prod, conso, x, y }
  const [position, setPosition] = useState({ coordinates: [2.5, 46.5], zoom: 1 })
  const [nuclearPlants, setNuclearPlants] = useState([])
  const [highlightedSource, setHighlightedSource] = useState(null)

  useEffect(() => {
    if (!showNuclearPlants) return
    let cancelled = false
    fetchProductionUnits({})
      .then(res => { if (!cancelled) setNuclearPlants((res.data || []).filter(u => u.psr_type === 'nuclear')) })
      .catch(() => { if (!cancelled) setNuclearPlants([]) })
    return () => { cancelled = true }
  }, [showNuclearPlants])

  const availableCodes = useMemo(() => new Set(regions.map(r => r.code_insee)), [regions])
  const selectedRegionName = regions.find(r => r.code_insee === selectedCode)?.region
  const maxProd = useMemo(
    () => Math.max(0, ...Object.values(regionTotals)),
    [regionTotals]
  )
  const nationalTotal = useMemo(
    () => Object.values(regionTotals).reduce((s, v) => s + v, 0),
    [regionTotals]
  )
  const maxLoad = useMemo(
    () => Math.max(0, ...Object.values(regionLoad)),
    [regionLoad]
  )
  const ribbonSpans = useMemo(() => mixSpans(mixSources || {}), [mixSources])
  const maxHighlightedMw = useMemo(() => {
    if (!highlightedSource) return 1
    return Math.max(1, ...Object.values(regionSources).map(s => s?.[highlightedSource] || 0))
  }, [highlightedSource, regionSources])

  return (
    <section className="glass-card map-card" data-testid="france-map">
      <div className="map-header">
        <h2 className="chart-title">
          {MODE_LABELS[mode]}
          {selectedRegionName && (
            <span className="map-selected-label"> — {selectedRegionName}</span>
          )}
        </h2>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {onModeChange && (
            <div className="tab-bar" role="tablist" aria-label="Mode de la carte" style={{ padding: 0 }}>
              {[
                { id: 'volume',  label: 'Volume' },
                { id: 'carbon',  label: 'Carbone' },
                { id: 'share',   label: 'Part nat.' },
                { id: 'balance', label: 'Export/Import' },
                { id: 'load',    label: 'Charge' },
                { id: 'curtailment', label: 'Curtailment' },
              ].filter(m => availableModes.includes(m.id)).map(m => (
                <button key={m.id} role="tab" aria-selected={mode === m.id}
                  className={`tab-bar__item${mode === m.id ? ' tab-bar__item--active' : ''}`}
                  onClick={() => onModeChange(m.id)}>
                  {m.label}
                </button>
              ))}
            </div>
          )}
          {selectedCode && (
            <button
              className="btn btn-ghost btn-xs"
              onClick={() => onSelect('')}
              title="Revenir à la vue nationale"
            >
              ← Vue nationale
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      ) : (
        <div className={`map-wrapper${showMixRibbon ? ' map-wrapper--ribbon' : ''}`}>
          <ComposableMap
            projection="geoMercator"
            projectionConfig={PROJECTION_CONFIG}
            width={600}
            height={460}
            style={{ width: '100%', height: '100%' }}
          >
            <ZoomableGroup
              zoom={position.zoom}
              center={position.coordinates}
              onMoveEnd={setPosition}
              minZoom={0.8}
              maxZoom={8}
            >
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map(geo => {
                  const code     = geo.properties.code
                  const nom      = geo.properties.nom
                  const isSelected = code === selectedCode
                  const hasData    = availableCodes.has(code)
                  const prod       = regionTotals[code] ?? 0
                  const conso      = regionConsommation[code] ?? null
                  const carbon     = regionCarbon[code] ?? null
                  const load       = regionLoad[code] ?? null
                  const curtailment = regionCurtailmentRisk[code] ?? null
                  const share      = nationalTotal > 0 ? (prod / nationalTotal) * 100 : 0
                  const balance    = conso != null && conso > 0 ? (prod - conso) / conso : null
                  const fill       = isSelected
                    ? '#2dd4bf'
                    : !hasData
                    ? '#1c2538'
                    : mode === 'carbon'
                    ? carbonColor(carbon)
                    : mode === 'balance'
                    ? balanceColor(balance)
                    : mode === 'load'
                    ? loadColor(load, maxLoad)
                    : mode === 'curtailment'
                    ? curtailmentColor(curtailment)
                    : volumeColor(prod, maxProd)

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onClick={() => hasData && onSelect(code)}
                      onMouseEnter={e => {
                        if (!hasData) return
                        setHovered({ name: nom, prod, conso, carbon, load, curtailment, share, balance, x: e.clientX, y: e.clientY })
                      }}
                      onMouseMove={e => {
                        if (hovered) setHovered(h => ({ ...h, x: e.clientX, y: e.clientY }))
                      }}
                      onMouseLeave={() => setHovered(null)}
                      style={{
                        default: {
                          fill,
                          stroke: isSelected ? '#5eead4' : 'rgba(45,212,191,0.4)',
                          strokeWidth: isSelected ? 2 : 0.8,
                          outline: 'none',
                          cursor: hasData ? 'pointer' : 'default',
                          transition: 'fill 0.25s',
                        },
                        hover: {
                          fill: hasData ? (isSelected ? '#5eead4' : '#0d9488') : '#19191c',
                          stroke: '#5eead4',
                          strokeWidth: 1.5,
                          outline: 'none',
                          cursor: hasData ? 'pointer' : 'default',
                        },
                        pressed: { fill: '#2dd4bf', outline: 'none' },
                      }}
                    />
                  )
                })
              }
            </Geographies>
            {highlightedSource && (
              <Geographies geography={GEO_URL}>
                {({ geographies }) =>
                  geographies
                    .filter(geo => availableCodes.has(geo.properties.code))
                    .map(geo => {
                      const code = geo.properties.code
                      const mw = regionSources[code]?.[highlightedSource]
                      if (!(mw > 0)) return null
                      const r = 4 + Math.sqrt(mw / maxHighlightedMw) * 16
                      const centroid = geoCentroid(geo)
                      return (
                        <Marker key={geo.rsmKey} coordinates={centroid}
                          onMouseEnter={e => setHovered({ name: geo.properties.nom, sourceMw: mw, x: e.clientX, y: e.clientY })}
                          onMouseMove={e => setHovered(h => (h && h.sourceMw != null ? { ...h, x: e.clientX, y: e.clientY } : h))}
                          onMouseLeave={() => setHovered(h => (h && h.sourceMw != null ? null : h))}>
                          <circle r={r} fill={SOURCE_COLORS[highlightedSource]} fillOpacity={0.55} stroke={SOURCE_COLORS[highlightedSource]} strokeWidth={1.5} />
                        </Marker>
                      )
                    })
                }
              </Geographies>
            )}
            {showNuclearPlants && nuclearPlants.map(plant => (
              <Marker key={plant.name} coordinates={[plant.lon, plant.lat]}
                onMouseEnter={e => setHovered(h => ({ ...(h || {}), plant: plant.name, x: e.clientX, y: e.clientY }))}
                onMouseMove={e => setHovered(h => (h && h.plant ? { ...h, x: e.clientX, y: e.clientY } : h))}
                onMouseLeave={() => setHovered(h => (h && h.plant ? null : h))}>
                <circle r={4} fill="#7c3aed" fillOpacity={0.85} stroke="#c4b5fd" strokeWidth={1} />
              </Marker>
            ))}
            </ZoomableGroup>
          </ComposableMap>

          {showMixRibbon && ribbonSpans.length > 0 && (() => {
            const cx = 96, cy = 148
            const capR = (RIBBON_R_OUTER - RIBBON_R_INNER) / 2
            const capMidR = (RIBBON_R_OUTER + RIBBON_R_INNER) / 2
            const startCap = polarToCartesian(cx, cy, capMidR, ARC_START)
            const endCap   = polarToCartesian(cx, cy, capMidR, ARC_END)
            const colorFor = key => highlightedSource === key ? SOURCE_COLORS[key] : mutedSourceColor(SOURCE_COLORS[key])
            return (
              <div className="mix-ribbon">
                <svg width={120} height={192} viewBox="0 0 120 192" className="mix-ribbon__svg">
                  {/* Rounded end caps — the arc's own start/end, not each wedge's */}
                  <circle cx={startCap.x} cy={startCap.y} r={capR} fill={colorFor(ribbonSpans[0].key)} />
                  <circle cx={endCap.x} cy={endCap.y} r={capR} fill={colorFor(ribbonSpans[ribbonSpans.length - 1].key)} />
                  {/* Wedges — each edge is a straight radius of the same circle, by construction.
                      Clicking one highlights that source's regional production on the map. */}
                  {ribbonSpans.map(s => (
                    <path
                      key={s.key}
                      d={annularSegmentPath(
                        cx, cy, RIBBON_R_INNER, RIBBON_R_OUTER,
                        ARC_START + s.start * (ARC_END - ARC_START),
                        ARC_START + s.end * (ARC_END - ARC_START)
                      )}
                      fill={colorFor(s.key)}
                      style={{ cursor: 'pointer', pointerEvents: 'auto' }}
                      onClick={() => setHighlightedSource(h => (h === s.key ? null : s.key))}
                    />
                  ))}
                  {/* One outline around the whole ring, not one per wedge */}
                  <path
                    d={ringOutlinePath(cx, cy, RIBBON_R_INNER, RIBBON_R_OUTER, ARC_START, ARC_END)}
                    fill="none"
                    stroke="var(--color-surface-2)"
                    strokeWidth={1}
                  />
                </svg>
                <div className="mix-ribbon__labels">
                  {ribbonSpans.filter(s => s.pct >= 6).map(s => {
                    const midAngle = ARC_START + ((s.start + s.end) / 2) * (ARC_END - ARC_START)
                    const labelPt = polarToCartesian(cx, cy, RIBBON_R_OUTER + 12, midAngle)
                    return (
                      <span
                        key={s.key}
                        className={`mix-ribbon__label${highlightedSource === s.key ? ' mix-ribbon__label--active' : ''}`}
                        style={{ left: `${labelPt.x}px`, top: `${labelPt.y}px`, color: colorFor(s.key) }}
                        onClick={() => setHighlightedSource(h => (h === s.key ? null : s.key))}
                      >
                        {SOURCE_LABELS[s.key]} <strong>{s.pct.toFixed(0)}%</strong>
                      </span>
                    )
                  })}
                </div>
              </div>
            )
          })()}

          {/* Floating tooltip */}
          {hovered && hovered.plant && (
            <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 32 }}>
              <strong>{hovered.plant}</strong>
              <span className="map-tooltip__value" style={{ color: '#c4b5fd' }}>Centrale nucléaire</span>
            </div>
          )}
          {hovered && hovered.sourceMw != null && (
            <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 32 }}>
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value" style={{ color: SOURCE_COLORS[highlightedSource] }}>
                {Math.round(hovered.sourceMw).toLocaleString('fr-FR')} MW · {SOURCE_LABELS[highlightedSource]}
              </span>
            </div>
          )}
          {hovered && !hovered.plant && hovered.sourceMw == null && (
            <div
              className="map-tooltip"
              style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 52 }}
            >
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value">
                {Math.round(hovered.prod).toLocaleString('fr-FR')} MW prod.
              </span>
              {mode === 'carbon' && hovered.carbon != null && (
                <span style={{ color: carbonColor(hovered.carbon), fontSize: '0.75rem' }}>
                  {hovered.carbon} gCO₂/kWh
                </span>
              )}
              {mode === 'load' && hovered.load != null && (
                <span style={{ color: loadColor(hovered.load, maxLoad), fontSize: '0.75rem' }}>
                  {hovered.load} % de la capacité installée consommée
                </span>
              )}
              {mode === 'curtailment' && (
                <span style={{ color: curtailmentColor(hovered.curtailment), fontSize: '0.75rem' }}>
                  {hovered.curtailment != null ? `${hovered.curtailment} % du surplus EnR national` : 'Pas de surplus enregistré'}
                </span>
              )}
              {mode === 'share' && (
                <span style={{ color: '#2dd4bf', fontSize: '0.75rem' }}>
                  {hovered.share.toFixed(1)} % de la prod. nationale
                </span>
              )}
              {mode === 'balance' && (
                <span style={{ color: hovered.balance >= 0 ? '#2dd4bf' : '#f59e0b', fontSize: '0.75rem' }}>
                  {hovered.balance != null ? `${hovered.balance >= 0 ? '+' : ''}${Math.round(hovered.balance * 100)} % vs sa conso.` : '—'}
                </span>
              )}
              {mode === 'volume' && hovered.conso != null && (
                <span style={{ color: '#f59e0b', fontSize: '0.75rem' }}>
                  {Math.round(hovered.conso).toLocaleString('fr-FR')} MW conso.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {!loading && mode === 'carbon' && (
        <div className="map-legend">
          <span className="map-legend__item" style={{ color: '#10b981' }}>● &lt;100</span>
          <span className="map-legend__item" style={{ color: '#84cc16' }}>● &lt;250</span>
          <span className="map-legend__item" style={{ color: '#f59e0b' }}>● &lt;400</span>
          <span className="map-legend__item" style={{ color: '#ef4444' }}>● ≥400 gCO₂/kWh</span>
        </div>
      )}
      {!loading && mode === 'balance' && (
        <div className="map-legend">
          <span className="map-legend__item" style={{ color: '#f59e0b' }}>● Importatrice</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, #f59e0b, rgb(45,40,24), rgb(24,45,44), #2dd4bf)` }}
          />
          <span className="map-legend__item" style={{ color: '#2dd4bf' }}>● Exportatrice</span>
        </div>
      )}
      {!loading && (mode === 'volume' || mode === 'share') && (
        <div className="map-legend">
          <span className="map-legend__item">{mode === 'share' ? 'Part nationale' : 'Production'}</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, rgb(${LOW_COLOR.join(',')}), rgb(${HIGH_COLOR.join(',')}))` }}
          />
          <span className="map-legend__item">faible → élevée</span>
          <span className="map-legend__item" style={{ color: '#4a5568' }}>● Pas de données</span>
        </div>
      )}
      {!loading && mode === 'load' && (
        <div className="map-legend">
          <span className="map-legend__item">Charge</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, rgb(${LOAD_LOW.join(',')}), rgb(${LOAD_HIGH.join(',')}))` }}
          />
          <span className="map-legend__item">faible → élevée</span>
          {showNuclearPlants && (
            <span className="map-legend__item" style={{ color: '#c4b5fd' }}>● Centrale nucléaire</span>
          )}
        </div>
      )}
      {!loading && mode === 'curtailment' && (
        <div className="map-legend">
          <span className="map-legend__item">Part du surplus EnR national</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, rgb(${CURTAIL_LOW.join(',')}), rgb(${CURTAIL_HIGH.join(',')}))` }}
          />
          <span className="map-legend__item">faible → élevée</span>
        </div>
      )}

      <p className="map-hint">
        {highlightedSource
          ? `${SOURCE_LABELS[highlightedSource]} en surbrillance — cliquez à nouveau sur le ruban pour réinitialiser`
          : selectedCode
          ? 'Cliquez sur une autre région pour comparer · ← Vue nationale pour revenir'
          : showMixRibbon
          ? 'Cliquez sur une région pour afficher son historique · cliquez sur le ruban pour explorer une source'
          : 'Cliquez sur une région pour afficher son historique'}
      </p>
    </section>
  )
})
