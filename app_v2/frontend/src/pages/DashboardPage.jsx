/**
 * DashboardPage — dataviz dashboard: KPIs, charts, map.
 * Fetches production/météo/capacity data from the FastAPI backend.
 * Public, no auth — portfolio showroom.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { KPICard } from '../components/KPICard.jsx'
import { FranceMap } from '../components/FranceMap.jsx'
import { CurtailmentRiskMap } from '../components/CurtailmentRiskMap.jsx'
import { HistoryChart } from '../components/HistoryChart.jsx'
import { CarbonBadge, computeCarbonIntensity } from '../components/CarbonBadge.jsx'
import { fetchProduction, fetchRegions, fetchMeteo, fetchCapacity, fetchCurtailmentRisk } from '../services/api.js'
import { ProdConsChart } from '../components/ProdConsChart.jsx'
import { RegionSelector } from '../components/RegionSelector.jsx'
import { MeteoChart } from '../components/MeteoChart.jsx'
import { CapacityChart } from '../components/CapacityChart.jsx'

// HistoryChart and CapacityChart are kept imported (even if not rendered) to preserve
// recharts module evaluation order in the production bundle — removing them shifts
// the circular-dep resolution and causes a TDZ crash.

const REFRESH_INTERVAL_MS = 15 * 60 * 1000  // 15 minutes

const SOURCE_LABELS = {
  nucleaire:   'Nucléaire',
  eolien:      'Éolien',
  solaire:     'Solaire',
  hydraulique: 'Hydraulique',
  gaz:         'Gaz',
  bioenergies: 'Bioénergies',
  charbon:     'Charbon',
  fioul:       'Fioul',
}

const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  gaz:         '#ef4444',
  bioenergies: '#84cc16',
  charbon:     '#6b7280',
  fioul:       '#f97316',
}

/** Aggregate multi-region data by timestamp (sum sources + conso). */
function aggregateByTimestamp(data) {
  const map = new Map()
  for (const r of data) {
    const ts = r.timestamp
    if (!map.has(ts)) map.set(ts, { timestamp: ts, sources: {}, consommation_mw: null, regions: new Set() })
    const agg = map.get(ts)
    agg.regions.add(r.code_insee)
    for (const [src, mw] of Object.entries(r.sources || {})) {
      if (typeof mw === 'number' && mw > 0) agg.sources[src] = (agg.sources[src] || 0) + mw
    }
    if (r.consommation_mw != null) agg.consommation_mw = (agg.consommation_mw || 0) + r.consommation_mw
  }

  const entries = Array.from(map.values())
  // RTE publishes region-by-region with a short delay — the freshest
  // timestamps often only have a handful of regions reported so far.
  // Summing an incomplete region set creates a misleading artificial cliff
  // at the edge of the chart, so drop any timestamp short of full coverage.
  const maxRegions = entries.reduce((max, e) => Math.max(max, e.regions.size), 0)
  return entries
    .filter(e => e.regions.size === maxRegions)
    .map(({ regions, ...rest }) => rest)
    .sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
}

/** Average meteo by timestamp across regions. */
function aggregateMeteoByTimestamp(data) {
  const map = new Map()
  for (const r of data) {
    const ts = r.timestamp
    if (!map.has(ts)) map.set(ts, { timestamp: ts, temp: 0, wind: 0, cloud: 0, n: 0 })
    const agg = map.get(ts)
    if (r.temperature_c  != null) agg.temp  += r.temperature_c
    if (r.wind_speed_10m != null) agg.wind  += r.wind_speed_10m
    if (r.cloudcover_pct != null) agg.cloud += r.cloudcover_pct
    agg.n++
  }
  return Array.from(map.values())
    .sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
    .map(r => ({
      timestamp:      r.timestamp,
      temperature_c:  r.n ? Math.round((r.temp  / r.n) * 10) / 10 : null,
      wind_speed_10m: r.n ? Math.round((r.wind  / r.n) * 10) / 10 : null,
      cloudcover_pct: r.n ? Math.round( r.cloud / r.n)            : null,
    }))
}

/** Colored chips showing current MW per source. */
function SourceChips({ sources }) {
  const entries = Object.entries(sources)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 7)
  if (!entries.length) return <span style={{ color: 'var(--color-text-muted)', fontSize: '0.8rem' }}>—</span>
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 6 }}>
      {entries.map(([src, mw]) => (
        <span key={src} style={{
          display: 'inline-flex', alignItems: 'center', gap: 4,
          padding: '2px 8px', borderRadius: 12, fontSize: '0.7rem', fontWeight: 600,
          background: (SOURCE_COLORS[src] || '#888') + '22',
          color: SOURCE_COLORS[src] || '#888',
          border: `1px solid ${(SOURCE_COLORS[src] || '#888')}55`,
        }}>
          {SOURCE_LABELS[src] || src} {Math.round(mw).toLocaleString('fr-FR')} MW
        </span>
      ))}
    </div>
  )
}

/** Sum all source MW from the last data point. */
function computeTotalMw(data) {
  if (!data.length) return 0
  const sources = data[data.length - 1].sources || {}
  return Math.round(Object.values(sources).reduce((sum, mw) => sum + (mw > 0 ? mw : 0), 0))
}

/** Return human-readable label of the dominant source at the last point. */
function computeDominantSource(data) {
  if (!data.length) return '—'
  const sources = data[data.length - 1].sources || {}
  const entries = Object.entries(sources).filter(([, v]) => v > 0)
  if (!entries.length) return '—'
  const [source] = entries.sort(([, a], [, b]) => b - a)[0]
  return SOURCE_LABELS[source] || source
}

function formatTime(date) {
  if (!date) return '—'
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

/** Return ISO date string (YYYY-MM-DD) for a Date offset by `days` from today. */
function isoDate(offsetDays = 0) {
  const d = new Date()
  d.setDate(d.getDate() + offsetDays)
  return d.toISOString().slice(0, 10)
}

export default function DashboardPage() {
  const [selectedRegion, setSelectedRegion] = useState('')
  const [regions, setRegions] = useState([])

  // globalData: all regions, unfiltered — used for choropleth coloring
  const [globalData, setGlobalData] = useState([])
  // productionData: filtered to selectedRegion (or all when '' after initial load)
  const [productionData, setProductionData] = useState([])

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastUpdated, setLastUpdated] = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  // Date range filter (default: last 7 days)
  const [startDate, setStartDate] = useState(isoDate(-7))
  const [endDate, setEndDate] = useState(isoDate(0))

  // Meteo + capacity data for drill-down
  const [meteoData, setMeteoData] = useState([])
  const [capacityData, setCapacityData] = useState([])
  const [drillLoading, setDrillLoading] = useState(false)

  // Curtailment risk: whole-history aggregate, independent of the region/date drill-down
  const [curtailmentData, setCurtailmentData] = useState([])
  const [curtailmentTotal, setCurtailmentTotal] = useState(0)
  const [curtailmentLoading, setCurtailmentLoading] = useState(true)

  /**
   * Load production data.
   * If regionCode is empty, result is stored in both globalData and productionData
   * (used as initial full-country fetch for choropleth).
   * If regionCode is set, only productionData is updated (globalData stays for choropleth).
   */
  const loadData = useCallback(async (regionCode, start, end, updateGlobal = false) => {
    try {
      setError(null)
      const params = { limit: 500, startDate: start, endDate: end }
      if (regionCode) params.regionCode = regionCode
      const result = await fetchProduction(params)
      const data = result.data || []
      setProductionData(data)
      if (updateGlobal || !regionCode) setGlobalData(data)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err.message || 'Erreur de chargement des données')
    }
  }, [])

  // Load meteo + capacity; when code is '' fetch France-level meteo (no region filter)
  const loadDrillData = useCallback(async (code, start, end) => {
    setDrillLoading(true)
    try {
      const meteoParams = code
        ? { regionCode: code, startDate: start, endDate: end }
        : { startDate: start, endDate: end }
      const [meteoRes, capacityRes] = await Promise.allSettled([
        fetchMeteo(meteoParams),
        code ? fetchCapacity({ regionCode: code }) : Promise.resolve({ data: [] }),
      ])
      setMeteoData(meteoRes.status === 'fulfilled' ? (meteoRes.value?.data || []) : [])
      setCapacityData(capacityRes.status === 'fulfilled' ? (capacityRes.value?.data || []) : [])
    } finally {
      setDrillLoading(false)
    }
  }, [])

  // Initial load: fetch all regions without filter (choropleth view)
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      const regsResult = await fetchRegions().catch(() => [])
      if (!cancelled) {
        setRegions(regsResult)
        // Load ALL regions data for the choropleth (no region filter)
        await loadData('', startDate, endDate, true)
        await loadDrillData('', startDate, endDate)
        setLoading(false)
      }
    })()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadData])

  // Curtailment risk map: fetched once, whole history — not tied to the region/date filters
  useEffect(() => {
    let cancelled = false
    fetchCurtailmentRisk()
      .then(result => {
        if (cancelled) return
        setCurtailmentData(result.data || [])
        setCurtailmentTotal(result.national_surplus_mwh_15min || 0)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setCurtailmentLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Region change: drill down into a specific region (or reset to global view)
  const handleRegionChange = useCallback(async (code) => {
    setSelectedRegion(code)
    setRefreshing(true)
    if (code) {
      // Drill-down: load selected region only
      await Promise.all([loadData(code, startDate, endDate), loadDrillData(code, startDate, endDate)])
    } else {
      // Back to global view: reload all-regions data + France meteo
      await Promise.all([loadData('', startDate, endDate, true), loadDrillData('', startDate, endDate)])
    }
    setRefreshing(false)
  }, [loadData, loadDrillData, startDate, endDate])

  // Date range change: reload data (preserve region selection)
  const handleDateChange = useCallback(async (newStart, newEnd) => {
    setRefreshing(true)
    if (selectedRegion) {
      // Keep choropleth up to date too
      await Promise.all([
        loadData(selectedRegion, newStart, newEnd),
        loadData('', newStart, newEnd, true).then(() => {}),
        loadDrillData(selectedRegion, newStart, newEnd),
      ])
    } else {
      await Promise.all([loadData('', newStart, newEnd, true), loadDrillData('', newStart, newEnd)])
    }
    setRefreshing(false)
  }, [loadData, loadDrillData, selectedRegion])

  // Auto-refresh every 15 min (AC #1 — "real-time")
  useEffect(() => {
    const id = setInterval(async () => {
      setRefreshing(true)
      if (selectedRegion) {
        await loadData(selectedRegion, startDate, endDate)
      } else {
        await loadData('', startDate, endDate, true)
      }
      setRefreshing(false)
    }, REFRESH_INTERVAL_MS)
    return () => clearInterval(id)
  }, [selectedRegion, startDate, endDate, loadData])

  // Compute per-region totals for choropleth (latest point per region)
  const { regionTotals, regionConsommation } = useMemo(() => {
    const latest = {}
    for (const r of globalData) {
      if (!latest[r.code_insee] || r.timestamp > latest[r.code_insee].timestamp) {
        latest[r.code_insee] = r
      }
    }
    const totals = {}
    const conso  = {}
    for (const [code, rec] of Object.entries(latest)) {
      totals[code] = Object.values(rec.sources).reduce((s, v) => s + (v > 0 ? v : 0), 0)
      if (rec.consommation_mw != null) conso[code] = rec.consommation_mw
    }
    return { regionTotals: totals, regionConsommation: conso }
  }, [globalData])

  // Aggregated data for charts (sum/average across all regions when no region selected)
  const aggregatedProdData = useMemo(
    () => selectedRegion ? productionData : aggregateByTimestamp(globalData),
    [selectedRegion, productionData, globalData]
  )
  const aggregatedMeteoData = useMemo(
    () => selectedRegion ? meteoData : aggregateMeteoByTimestamp(meteoData),
    [selectedRegion, meteoData]
  )

  // Derive KPIs from current data (region-specific or global)
  const displayData = selectedRegion ? productionData : globalData
  const lastSources = displayData.length
    ? (displayData[displayData.length - 1].sources || {})
    : {}
  const totalMw = computeTotalMw(displayData)
  const dominantSource = computeDominantSource(displayData)
  const carbonIntensity = computeCarbonIntensity(lastSources)

  // Sparkline data: carbon intensity per time point (last 96 points max)
  const sparkData = useMemo(() =>
    displayData.slice(-96).map(r => ({
      t: r.timestamp,
      v: computeCarbonIntensity(r.sources || {}),
    })),
    [displayData]
  )

  const selectedRegionName = regions.find(r => r.code_insee === selectedRegion)?.region

  return (
    <main id="main-content" className="app-main">

      {/* Region selector + refresh status + date range */}
      <div className="dashboard-toolbar">
        <RegionSelector
          regions={regions}
          selected={selectedRegion}
          onChange={handleRegionChange}
          loading={loading}
        />

        <div className="date-bar" data-testid="date-range">
          <span className="selector-label">Période :</span>
          <input id="date-start" type="date" className="selector-input date-bar__input"
            value={startDate} max={endDate} aria-label="Date de début" data-testid="date-start"
            onChange={e => { setStartDate(e.target.value); handleDateChange(e.target.value, endDate) }} />
          <span className="selector-label" aria-hidden="true">→</span>
          <input id="date-end" type="date" className="selector-input date-bar__input"
            value={endDate} min={startDate} max={isoDate(0)} aria-label="Date de fin" data-testid="date-end"
            onChange={e => { setEndDate(e.target.value); handleDateChange(startDate, e.target.value) }} />
          {[{ label: '24h', days: -1 }, { label: '7j', days: -7 }, { label: '30j', days: -30 }].map(({ label, days }) => (
            <button key={label} className="btn btn-ghost btn-xs" onClick={() => {
              const s = isoDate(days); const e = isoDate(0)
              setStartDate(s); setEndDate(e); handleDateChange(s, e)
            }}>{label}</button>
          ))}
        </div>

        <div className="dashboard-toolbar__status">
          {(loading || refreshing) && (
            <span
              className="refresh-dot"
              title="Actualisation en cours…"
              aria-label="Actualisation en cours"
              data-testid="refresh-indicator"
            />
          )}
          {lastUpdated && (
            <span className="last-updated" data-testid="last-updated">
              Màj {formatTime(lastUpdated)}
            </span>
          )}
        </div>
      </div>

      {/* ── KPI strip ────────────────────────────────────────── */}
      <div className="kpi-grid" data-testid="kpi-grid">
        <KPICard
          title={selectedRegionName ? `Production — ${selectedRegionName}` : 'Production France'}
          value={totalMw.toLocaleString('fr-FR')} unit="MW" loading={loading}
        />
        <div className="glass-card kpi-card">
          <p className="kpi-title">Mix énergétique</p>
          {loading ? <p className="kpi-value">—</p> : <SourceChips sources={lastSources} />}
        </div>
        <CarbonBadge intensity={carbonIntensity} sparkData={sparkData} loading={loading} />
        <KPICard
          title={selectedRegion ? 'Points de données' : 'Régions actives'}
          value={selectedRegion ? productionData.length : Object.keys(regionTotals).length}
          loading={loading}
        />
      </div>

      {/* ── 2×2 grid : [prod/conso | sources] / [carte | météo] ── */}
      <div className="hero-grid">
        {/* Ligne 1 gauche — prod vs conso */}
        <ProdConsChart
          data={aggregatedProdData}
          region={selectedRegionName}
          loading={loading || refreshing}
        />
        {/* Ligne 1 droite — stacked par source */}
        <HistoryChart
          data={aggregatedProdData}
          region={selectedRegionName || 'France'}
          loading={loading || refreshing}
        />
        {/* Ligne 2 gauche — carte France */}
        <FranceMap
          regions={regions}
          regionTotals={regionTotals}
          regionConsommation={regionConsommation}
          selectedCode={selectedRegion}
          onSelect={handleRegionChange}
          loading={loading}
        />
        {/* Ligne 2 droite — météo */}
        {error ? (
          <div className="glass-card chart-card chart-error" data-testid="app-error">
            <p>Erreur : {error}</p>
          </div>
        ) : (
          <MeteoChart
            data={aggregatedMeteoData}
            region={selectedRegionName}
            loading={drillLoading}
          />
        )}
      </div>

      {/* ── Surplus renouvelable & prix négatifs ────────────────── */}
      <div className="hero-grid hero-grid--single">
        <CurtailmentRiskMap
          data={curtailmentData}
          nationalSurplus={curtailmentTotal}
          loading={curtailmentLoading}
        />
      </div>

    </main>
  )
}
