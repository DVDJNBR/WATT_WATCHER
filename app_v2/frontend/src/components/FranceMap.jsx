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

/**
 * Map delta (prod - conso) / conso to a semantic colour.
 *   > +15% → rouge   (sur-production, risque prix négatifs)
 *   ±15%   → vert    (équilibre)
 *   < -15% → orange  (sous-production, dépendance import)
 *   no data → gris
 */
function deltaColor(prod, conso) {
  if (conso == null || conso === 0) {
    // No consumption data — fall back to neutral blue gradient hint
    return prod > 0 ? '#2d6bcd' : '#1c2538'
  }
  const ratio = (prod - conso) / conso
  if (ratio > 0.15)  return '#ef4444'  // sur-production — rouge
  if (ratio < -0.15) return '#f59e0b'  // sous-production — orange
  return '#10b981'                      // équilibre — vert
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
                    ? '#4f8ef7'
                    : hasData
                    ? deltaColor(prod, conso)
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
                          stroke: isSelected ? '#7eb5ff' : 'rgba(79,142,247,0.4)',
                          strokeWidth: isSelected ? 2 : 0.8,
                          outline: 'none',
                          cursor: hasData ? 'pointer' : 'default',
                          transition: 'fill 0.25s',
                        },
                        hover: {
                          fill: hasData ? (isSelected ? '#6aa3ff' : '#2d6bcd') : '#111827',
                          stroke: '#7eb5ff',
                          strokeWidth: 1.5,
                          outline: 'none',
                          cursor: hasData ? 'pointer' : 'default',
                        },
                        pressed: { fill: '#4f8ef7', outline: 'none' },
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
                ⚡ {Math.round(hovered.prod).toLocaleString('fr-FR')} MW prod.
              </span>
              {hovered.conso != null && (
                <span style={{ color: '#f59e0b', fontSize: '0.75rem' }}>
                  🏠 {Math.round(hovered.conso).toLocaleString('fr-FR')} MW conso.
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Semantic legend */}
      {!loading && (
        <div className="map-legend">
          <span className="map-legend__item" style={{ color: '#10b981' }}>● Équilibre</span>
          <span className="map-legend__item" style={{ color: '#ef4444' }}>● Sur-production</span>
          <span className="map-legend__item" style={{ color: '#f59e0b' }}>● Sous-production</span>
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
