/**
 * FranceMap — choropleth map of the 13 French metropolitan regions.
 *
 * Each region is colored by its latest total production (MW) — dark blue
 * for low, bright blue for high. Hovering shows name + value.
 * Clicking a region triggers onSelect(code_insee) for drill-down.
 */
import { memo, useState, useMemo } from 'react'
import { ComposableMap, Geographies, Geography } from 'react-simple-maps'

const GEO_URL = '/france-regions.geojson'

const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2900 }

/** Linear interpolation between two RGB colours based on t ∈ [0, 1]. */
function lerpColor(r1, g1, b1, r2, g2, b2, t) {
  return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`
}

/**
 * Map a production value to a fill colour on a blue scale.
 * Low → #1c2538 (surface-2), High → #4f8ef7 (accent).
 */
function productionColor(value, minVal, maxVal) {
  if (!value || minVal === maxVal) return '#1c2538'
  const t = Math.max(0, Math.min(1, (value - minVal) / (maxVal - minVal)))
  return lerpColor(28, 37, 56, 79, 142, 247, t)
}

/**
 * @param {{
 *   regions: Array<{code_insee:string, region:string}>,
 *   regionTotals: Object,   // { [code_insee]: totalMW }
 *   selectedCode: string,
 *   onSelect: Function,
 *   loading?: boolean,
 * }} props
 */
export const FranceMap = memo(function FranceMap({
  regions = [],
  regionTotals = {},
  selectedCode,
  onSelect,
  loading = false,
}) {
  const [hovered, setHovered] = useState(null) // { name, value, x, y }

  const availableCodes = useMemo(() => new Set(regions.map(r => r.code_insee)), [regions])
  const selectedRegionName = regions.find(r => r.code_insee === selectedCode)?.region

  // Choropleth scale bounds
  const totalsArr = Object.values(regionTotals).filter(Boolean)
  const minVal = totalsArr.length ? Math.min(...totalsArr) : 0
  const maxVal = totalsArr.length ? Math.max(...totalsArr) : 1

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
            <Geographies geography={GEO_URL}>
              {({ geographies }) =>
                geographies.map(geo => {
                  const code     = geo.properties.code
                  const nom      = geo.properties.nom
                  const isSelected = code === selectedCode
                  const hasData    = availableCodes.has(code)
                  const total      = regionTotals[code]
                  const fill       = isSelected
                    ? '#4f8ef7'
                    : hasData
                    ? productionColor(total, minVal, maxVal)
                    : '#111827'

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onClick={() => hasData && onSelect(code)}
                      onMouseEnter={e => {
                        if (!hasData) return
                        const val = total ? `${Math.round(total).toLocaleString('fr-FR')} MW` : '—'
                        setHovered({ name: nom, value: val, x: e.clientX, y: e.clientY })
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
          </ComposableMap>

          {/* Floating tooltip */}
          {hovered && (
            <div
              className="map-tooltip"
              style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 38 }}
            >
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value">{hovered.value}</span>
            </div>
          )}
        </div>
      )}

      {/* Colour legend */}
      {!loading && totalsArr.length > 0 && (
        <div className="map-legend">
          <span className="map-legend__label">{Math.round(minVal).toLocaleString('fr-FR')} MW</span>
          <div className="map-legend__bar" />
          <span className="map-legend__label">{Math.round(maxVal).toLocaleString('fr-FR')} MW</span>
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
