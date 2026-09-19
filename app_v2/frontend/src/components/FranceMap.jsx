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
 */
import { memo, useState, useMemo } from 'react'
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps'
import { geoCentroid } from 'd3-geo'

const GEO_URL = '/france-regions.geojson'

const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2200 }

const LOW_COLOR  = [24, 45, 44]     // dim, desaturated teal
const HIGH_COLOR = [45, 212, 191]   // #2dd4bf — accent teal

function lerp(a, b, t) { return Math.round(a + (b - a) * t) }

/** Interpolate a teal intensity from production volume relative to the region max. */
function volumeColor(prod, maxProd) {
  const t = maxProd > 0 ? Math.min(1, Math.max(0, prod / maxProd)) : 0
  const [r, g, b] = LOW_COLOR.map((c, i) => lerp(c, HIGH_COLOR[i], t))
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
  selectedCode,
  onSelect,
  loading = false,
  mode = 'volume',       // 'volume' | 'carbon' | 'share' | 'balance'
  onModeChange = null,   // (mode) => void — omit to hide the toggle
  availableModes = ['volume', 'carbon', 'share'],
}) {
  const [hovered, setHovered] = useState(null)   // { name, prod, conso, x, y }
  const [position, setPosition] = useState({ coordinates: [2.5, 46.5], zoom: 1 })

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
        <div className="map-wrapper">
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
                    : volumeColor(prod, maxProd)

                  return (
                    <Geography
                      key={geo.rsmKey}
                      geography={geo}
                      onClick={() => hasData && onSelect(code)}
                      onMouseEnter={e => {
                        if (!hasData) return
                        setHovered({ name: nom, prod, conso, carbon, share, balance, x: e.clientX, y: e.clientY })
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
            {mode === 'volume' && (
              <Geographies geography={GEO_URL}>
                {({ geographies }) =>
                  geographies
                    .filter(geo => availableCodes.has(geo.properties.code) && geo.properties.code !== selectedCode)
                    .map(geo => {
                      const code = geo.properties.code
                      const prod = regionTotals[code] ?? 0
                      const pct = nationalTotal > 0 ? (prod / nationalTotal) * 100 : 0
                      const centroid = geoCentroid(geo)
                      return (
                        <Marker key={geo.rsmKey} coordinates={centroid}>
                          <text textAnchor="middle" y={-2} className="map-region-label"
                            style={{ fontSize: 9, fontWeight: 700, fill: '#fff', pointerEvents: 'none' }}>
                            {Math.round(prod).toLocaleString('fr-FR')} MW
                          </text>
                          <text textAnchor="middle" y={9} className="map-region-label"
                            style={{ fontSize: 8, fontWeight: 600, fill: '#fff', opacity: 0.95, pointerEvents: 'none' }}>
                            {pct.toFixed(1)}%
                          </text>
                        </Marker>
                      )
                    })
                }
              </Geographies>
            )}
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
              {mode === 'carbon' && hovered.carbon != null && (
                <span style={{ color: carbonColor(hovered.carbon), fontSize: '0.75rem' }}>
                  {hovered.carbon} gCO₂/kWh
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

      <p className="map-hint">
        {selectedCode
          ? 'Cliquez sur une autre région pour comparer · ← Vue nationale pour revenir'
          : 'Cliquez sur une région pour afficher son historique'}
      </p>
    </section>
  )
})
