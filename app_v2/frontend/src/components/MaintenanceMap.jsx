/**
 * MaintenanceMap — every production unit as a pin, red = currently flagged
 * by an ENTSO-E outage event. Matching is fuzzy (uppercase substring on
 * unit name) since fact_maintenance.unit_name ("RANCE", "MONTEZIC") doesn't
 * share a stable id with the geolocated unit registry ("Rance", "Montezic 3")
 * — some smaller/ungeolocated plants in an outage won't find a pin to color;
 * that's a real registry-coverage gap, not silently hidden.
 */
import { memo, useEffect, useState } from 'react'
import { ComposableMap, Geographies, Geography, Marker, ZoomableGroup } from 'react-simple-maps'
import { fetchProductionUnits } from '../services/api.js'

const GEO_URL = '/france-regions.geojson'
const PROJECTION_CONFIG = { center: [2.5, 46.5], scale: 2200 }

export function normalize(name) {
  return (name || '').toUpperCase().replace(/[^A-Z0-9]/g, ' ').trim()
}

function isUnderMaintenance(unitName, maintenanceTokens) {
  const norm = normalize(unitName)
  return maintenanceTokens.some(token => token && (norm.includes(token) || token.includes(norm)))
}

export const MaintenanceMap = memo(function MaintenanceMap({ maintenanceEvents = [], loading = false }) {
  const [units, setUnits] = useState([])
  const [unitsLoading, setUnitsLoading] = useState(true)
  const [hovered, setHovered] = useState(null)

  useEffect(() => {
    let cancelled = false
    fetchProductionUnits({})
      .then(res => { if (!cancelled) setUnits(res.data || []) })
      .catch(() => { if (!cancelled) setUnits([]) })
      .finally(() => { if (!cancelled) setUnitsLoading(false) })
    return () => { cancelled = true }
  }, [])

  const maintenanceTokens = maintenanceEvents.map(e => normalize(e.unit_name)).filter(Boolean)
  const flaggedCount = units.filter(u => isUnderMaintenance(u.name, maintenanceTokens)).length

  return (
    <section className="glass-card map-card" data-testid="maintenance-map">
      <div className="map-header">
        <h2 className="chart-title" title="Postes de production géolocalisés — en rouge, ceux concernés par un événement d'indisponibilité ENTSO-E en cours ou à venir.">
          Postes de production — maintenance
        </h2>
      </div>

      {(loading || unitsLoading) ? (
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      ) : (
        <div className="map-wrapper">
          <ComposableMap projection="geoMercator" projectionConfig={PROJECTION_CONFIG} width={600} height={460} style={{ width: '100%', height: '100%' }}>
            <ZoomableGroup minZoom={0.8} maxZoom={8}>
              <Geographies geography={GEO_URL}>
                {({ geographies }) => geographies.map(geo => (
                  <Geography key={geo.rsmKey} geography={geo}
                    style={{
                      default: { fill: '#171512', stroke: 'rgba(45,212,191,0.3)', strokeWidth: 0.8, outline: 'none' },
                      hover: { fill: '#171512', stroke: 'rgba(45,212,191,0.3)', strokeWidth: 0.8, outline: 'none' },
                      pressed: { fill: '#171512', outline: 'none' },
                    }} />
                ))}
              </Geographies>
              {units.map(unit => {
                const flagged = isUnderMaintenance(unit.name, maintenanceTokens)
                return (
                  <Marker key={unit.name} coordinates={[unit.lon, unit.lat]}
                    onMouseEnter={e => setHovered({ name: unit.name, flagged, x: e.clientX, y: e.clientY })}
                    onMouseMove={e => hovered && setHovered(h => ({ ...h, x: e.clientX, y: e.clientY }))}
                    onMouseLeave={() => setHovered(null)}>
                    <circle r={flagged ? 5 : 3} fill={flagged ? '#ef4444' : '#2dd4bf'} fillOpacity={flagged ? 0.9 : 0.55}
                      stroke={flagged ? '#fca5a5' : 'none'} strokeWidth={flagged ? 1 : 0} />
                  </Marker>
                )
              })}
            </ZoomableGroup>
          </ComposableMap>

          {hovered && (
            <div className="map-tooltip" style={{ position: 'fixed', left: hovered.x + 14, top: hovered.y - 40 }}>
              <strong>{hovered.name}</strong>
              <span className="map-tooltip__value" style={{ color: hovered.flagged ? '#ef4444' : '#2dd4bf' }}>
                {hovered.flagged ? 'En maintenance' : 'En service'}
              </span>
            </div>
          )}
        </div>
      )}

      <div className="map-legend">
        <span className="map-legend__item" style={{ color: '#2dd4bf' }}>● En service</span>
        <span className="map-legend__item" style={{ color: '#ef4444' }}>● En maintenance ({flaggedCount})</span>
      </div>
    </section>
  )
})
