/**
 * CurtailmentRiskMap — which regions actually drove negative-price events.
 *
 * Colors each region by its share of the NATIONAL wind+solar surplus (over
 * its own consumption) summed across every 15-min slot where the national
 * price went negative. Deliberately renewable-only, same reasoning as
 * FranceMap's rejection of a raw regional prod/conso ratio: nuclear-heavy
 * regions structurally export several times their own consumption at all
 * times, so including nuclear would just re-surface that permanent export
 * pattern instead of the actual, curtailable oversupply RTE throttles.
 *
 * There is no per-region negative price in France (single EPEX bidding
 * zone) — this map answers a different, real question: "which region's
 * renewable output pushed the *national* price negative", not "what was
 * the price here".
 */
import { memo, useState, useMemo } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'

const GEO_URL = '/france-regions.geojson'
const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2200 }

const LOW_COLOR  = [24, 45, 44]     // dim, desaturated teal — matches FranceMap
const HIGH_COLOR = [245, 158, 11]   // #f59e0b amber — distinct from the volume map's teal

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

function riskColor(sharePct) {
  const t = Math.min(1, Math.max(0, sharePct / 100))
  const [r, g, b] = LOW_COLOR.map((c, i) => lerp(c, HIGH_COLOR[i], t))
  return `rgb(${r}, ${g}, ${b})`
}

/**
 * @param {{
 *   data: Array<{code_insee:string, region:string, share_pct:number, surplus_mwh_15min:number, n_slots:number}>,
 *   nationalSurplus: number,
 *   loading?: boolean,
 * }} props
 */
export const CurtailmentRiskMap = memo(function CurtailmentRiskMap({
  data = [],
  nationalSurplus = 0,
  loading = false,
}) {
  const [hovered, setHovered] = useState(null)

  const byCode = useMemo(() => {
    const m = {}
    for (const r of data) m[r.code_insee] = r
    return m
  }, [data])

  return (
    <section className="glass-card map-card" data-testid="curtailment-risk-map">
      <div className="map-header">
        <h2 className="chart-title">Contribution au surplus renouvelable (prix négatifs)</h2>
      </div>

      {loading ? (
        <div className="skeleton" style={{ height: 420 }} />
      ) : (
        <div className="map-wrapper">
          <ComposableMap
            projection="geoMercator"
            projectionConfig={PROJECTION_CONFIG}
            width={600}
            height={460}
            style={{ width: '100%', height: 'auto' }}
          >
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map(geo => {
                  const code = geo.properties.code
                  const nom  = geo.properties.nom
                  const r    = byCode[code]
                  const fill = r ? riskColor(r.share_pct) : '#1c2538'

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onMouseEnter={e => {
                        if (!r) return
                        setHovered({ name: nom, ...r, x: e.clientX, y: e.clientY })
                      }}
                      onMouseMove={e => {
                        if (hovered) setHovered(h => ({ ...h, x: e.clientX, y: e.clientY }))
                      }}
                      onMouseLeave={() => setHovered(null)}
                      style={{
                        default: {
                          fill,
                          stroke: 'rgba(245,158,11,0.4)',
                          strokeWidth: 0.8,
                          outline: 'none',
                        },
                        hover: {
                          fill: r ? '#f59e0b' : '#19191c',
                          stroke: '#fbbf24',
                          strokeWidth: 1.5,
                          outline: 'none',
                        },
                        pressed: { outline: 'none' },
                      }}
                    />
                  )
                })
              }
            </Geographies>
          </ComposableMap>

          {hovered && (
            <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 60 }}>
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value">{hovered.share_pct}% du surplus national</span>
              <span style={{ color: '#a1a1aa', fontSize: '0.75rem' }}>
                {Math.round(hovered.surplus_mwh_15min).toLocaleString('fr-FR')} MW cumulés · {hovered.n_slots} créneaux
              </span>
            </div>
          )}
        </div>
      )}

      {!loading && (
        <div className="map-legend">
          <span className="map-legend__item">Part du surplus</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, rgb(${LOW_COLOR.join(',')}), rgb(${HIGH_COLOR.join(',')}))` }}
          />
          <span className="map-legend__item">faible → élevée</span>
        </div>
      )}

      <p className="map-hint">
        Éolien + solaire uniquement (nucléaire exclu — export structurel, pas un signal de surproduction) ·
        surplus cumulé sur tous les créneaux à prix national négatif · pas de prix par région, la France est une zone de marché unique.
      </p>
    </section>
  )
})
