/**
 * FranceMap — choropleth map of the 13 French metropolitan regions.
 *
 * Each region is colored by its latest total production (MW) — dark blue
 * for low, bright blue for high. Hovering shows name + value.
 * Clicking a region triggers onSelect(code_insee) for drill-down.
 */
import { memo, useState, useMemo } from 'react'
import { ComposableMap, Geographies, Geography, ZoomableGroup } from 'react-simple-maps'

const GEO_URL = '/france-regions.geojson'

const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2200 }

// A per-region prod/conso ratio isn't a meaningful "surproduction" signal:
// French regions aren't independent grids — nuclear-heavy regions
// structurally export several times their own consumption to neighbouring
// regions as their permanent, normal state (e.g. Centre-Val de Loire sits
// around +300% essentially always), while import-dependent regions like
// Île-de-France sit permanently around -95%. There is no fixed threshold
// that means "anomaly" across regions this different — so the map colours
// by production volume instead, and the one place that surfaces a
// (nationally calibrated) surplus signal is the production/consumption
// chart, where prod-vs-conso is at least measured on the same national
// market the French price actually clears on.

const LOW_COLOR  = [24, 45, 44]     // dim, desaturated teal
const HIGH_COLOR = [45, 212, 191]   // #2dd4bf — accent teal

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

/** Interpolate a teal intensity from production volume relative to the region max. */
function volumeColor(prod, maxProd) {
  const t = maxProd > 0 ? Math.min(1, Math.max(0, prod / maxProd)) : 0
  const [r, g, b] = LOW_COLOR.map((c, i) => lerp(c, HIGH_COLOR[i], t))
  return `rgb(${r}, ${g}, ${b})`
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
  selectedCode,
  onSelect,
  loading = false,
}) {
  const [hovered, setHovered] = useState(null)   // { name, prod, conso, x, y }
  const [position, setPosition] = useState({ coordinates: [2.5, 46.5], zoom: 1 })

  const availableCodes = useMemo(() => new Set(regions.map(r => r.code_insee)), [regions])
  const selectedRegionName = regions.find(r => r.code_insee === selectedCode)?.region
  const maxProd = useMemo(
    () => Math.max(0, ...Object.values(regionTotals)),
    [regionTotals]
  )

  return (
    <section className="glass-card map-card" data-testid="france-map">
      <div className="map-header">
        <h2 className="chart-title">
          Production par région
          {selectedRegionName && (
            <span className="map-selected-label"> — {selectedRegionName}</span>
          )}
        </h2>
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
                  const fill       = isSelected
                    ? '#2dd4bf'
                    : hasData
                    ? volumeColor(prod, maxProd)
                    : '#1c2538'

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onClick={() => hasData && onSelect(code)}
                      onMouseEnter={e => {
                        if (!hasData) return
                        setHovered({ name: nom, prod, conso, x: e.clientX, y: e.clientY })
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
            </ZoomableGroup>
          </ComposableMap>

          {/* Floating tooltip */}
          {hovered && (
            <div
              className="map-tooltip"
              style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 52 }}
            >
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value">
                {Math.round(hovered.prod).toLocaleString('fr-FR')} MW prod.
              </span>
              {hovered.conso != null && (
                <span style={{ color: '#f59e0b', fontSize: '0.75rem' }}>
                  {Math.round(hovered.conso).toLocaleString('fr-FR')} MW conso.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Volume legend */}
      {!loading && (
        <div className="map-legend">
          <span className="map-legend__item">Production</span>
          <span
            className="map-legend__gradient"
            style={{ background: `linear-gradient(90deg, rgb(${LOW_COLOR.join(',')}), rgb(${HIGH_COLOR.join(',')}))` }}
          />
          <span className="map-legend__item">faible → élevée</span>
          <span className="map-legend__item" style={{ color: '#4a5568' }}>● Pas de données</span>
        </div>
      )}

      <p className="map-hint">
        {selectedCode
          ? 'Cliquez sur une autre région pour comparer · ← Vue nationale pour revenir'
          : 'Cliquez sur une région pour afficher l\'historique de production'}
      </p>
    </section>
  )
})
