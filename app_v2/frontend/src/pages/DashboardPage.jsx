/**
 * DashboardPage — dataviz dashboard: KPIs, charts, map.
 * Fetches production/météo/capacity data from the FastAPI backend.
 * Public, no auth — portfolio showroom.
 *
 * Focused on the app's actual story — anticipating curtailment (negative
 * prices forcing wind/solar offline) driven by low consumption + favorable
 * weather — not a feature showcase. Tabs: Production & consommation (the
 * surplus story) / Prix (négatifs, business framing) / Capacité (installed
 * vs used, maintenance).
 */
import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { KPICard } from '../components/KPICard.jsx'
import { FranceMap } from '../components/FranceMap.jsx'
import { CurtailmentCalendar } from '../components/CurtailmentCalendar.jsx'
import { HistoryChart } from '../components/HistoryChart.jsx'
import { computeCarbonIntensity } from '../components/CarbonGauge.jsx'
import { CapacityFactorChart } from '../components/CapacityFactorChart.jsx'
import { MaintenanceMap, normalize as normalizeUnitName } from '../components/MaintenanceMap.jsx'
import { PriceTrendChart } from '../components/PriceTrendChart.jsx'
import {
  fetchAllProduction, fetchRegions, fetchMeteo, fetchCapacity, fetchCurtailmentCalendar, fetchCurtailmentRisk,
  fetchMaintenance, fetchProductionUnits, fetchMarketPrice,
} from '../services/api.js'
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
  bioenergies: 'Bioénergies',
  thermique:   'Thermique fossile',
}

const SOURCE_COLORS = {
  nucleaire:   '#7c3aed',
  eolien:      '#10b981',
  solaire:     '#f59e0b',
  hydraulique: '#3b82f6',
  bioenergies: '#84cc16',
  thermique:   '#ef4444',
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

/** Average MW per source across a time series (for capacity-factor). */
function averageBySource(data) {
  const sums = {}
  const counts = {}
  for (const row of data) {
    for (const [src, mw] of Object.entries(row.sources || {})) {
      if (typeof mw !== 'number' || mw <= 0) continue
      sums[src] = (sums[src] || 0) + mw
      counts[src] = (counts[src] || 0) + 1
    }
  }
  const avg = {}
  for (const src of Object.keys(sums)) avg[src] = sums[src] / counts[src]
  return avg
}

/** Latest installed MW per source, summed across regions when capacityData spans several. */
function latestCapacityBySource(capacityData) {
  const bySource = {}
  for (const row of capacityData) {
    // Pre-existing data bug in fact_capacity/dim_region (not introduced here): some
    // rows carry a float-stringified code_insee ("24.0" instead of "24", or "nan") from
    // a past ingestion run, each paired with a capacity value inflated x1000 — skip them
    // rather than double-count a region's capacity 1000x. Worth a real backend fix later.
    if (!row.code_insee || row.code_insee.includes('.') || row.code_insee === 'nan') continue
    const key = `${row.code_insee}_${row.source}`
    if (!bySource[key] || (row.annee && row.annee > bySource[key].annee)) bySource[key] = row
  }
  const totals = {}
  for (const row of Object.values(bySource)) {
    if (row.puissance_installee_mw == null) continue
    totals[row.source] = (totals[row.source] || 0) + row.puissance_installee_mw
  }
  return totals
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
  // Tracks the most recently requested range so a slow, superseded fetch
  // (fired by an earlier preset click) can't overwrite the chart after a
  // faster later click already landed — see loadData/loadDrillData.
  const latestRangeRef = useRef({ start: startDate, end: endDate })

  // Meteo + capacity data for drill-down
  const [meteoData, setMeteoData] = useState([])
  const [capacityData, setCapacityData] = useState([])
  const [drillLoading, setDrillLoading] = useState(false)

  // Negative-price calendar: whole-history aggregate, independent of the region/date drill-down
  const [calendarDays, setCalendarDays] = useState([])
  const [calendarRange, setCalendarRange] = useState(null)
  const [calendarStats, setCalendarStats] = useState(null)
  const [calendarLoading, setCalendarLoading] = useState(true)

  // Curtailment risk by region: whole-history, drives the map's default mode —
  // which regions actually drive curtailment (wind+solar surplus during
  // negative-price windows), not just who produces the most.
  const [curtailmentRiskData, setCurtailmentRiskData] = useState([])

  // Day-ahead spot price over time — Consommation tab. National (no region
  // filter), follows the shared date range like production/météo.
  const [marketPriceData, setMarketPriceData] = useState([])
  const [priceLoading, setPriceLoading] = useState(true)

  // Maintenance events — Capacité tab
  const [maintenanceEvents, setMaintenanceEvents] = useState([])
  const [maintenanceLoading, setMaintenanceLoading] = useState(true)

  // All production units — fetched once, used to enrich maintenance events with a region
  // (fact_maintenance.id_region isn't populated at ingestion) via the same fuzzy name match
  // MaintenanceMap uses for its pins.
  const [allUnits, setAllUnits] = useState([])
  useEffect(() => {
    let cancelled = false
    fetchProductionUnits({}).then(res => { if (!cancelled) setAllUnits(res.data || []) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  /**
   * Load production data.
   * If regionCode is empty, result is stored in both globalData and productionData
   * (used as initial full-country fetch for choropleth).
   * If regionCode is set, only productionData is updated (globalData stays for choropleth).
   */
  const loadData = useCallback(async (regionCode, start, end, updateGlobal = false) => {
    try {
      setError(null)
      const params = { startDate: start, endDate: end }
      if (regionCode) params.regionCode = regionCode
      const result = await fetchAllProduction(params)
      // A later preset click may have already moved the requested range on
      // while this fetch was still in flight — drop it rather than clobber
      // the chart with an older range's data.
      if (start !== latestRangeRef.current.start || end !== latestRangeRef.current.end) return
      // API returns newest-first (DESC) per page; consumers (KPI "latest point"
      // logic, charts) assume ascending chronological order.
      const data = (result.data || []).sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
      setProductionData(data)
      if (updateGlobal || !regionCode) setGlobalData(data)
      setLastUpdated(new Date())
    } catch (err) {
      if (start === latestRangeRef.current.start && end === latestRangeRef.current.end) {
        setError(err.message || 'Erreur de chargement des données')
      }
    }
  }, [])

  // Load meteo + capacity; when code is '' fetch France-level meteo + all-region capacity
  const loadDrillData = useCallback(async (code, start, end) => {
    setDrillLoading(true)
    try {
      const meteoParams = code
        ? { regionCode: code, startDate: start, endDate: end, limit: 5000 }
        : { startDate: start, endDate: end, limit: 5000 }
      const [meteoRes, capacityRes] = await Promise.allSettled([
        fetchMeteo(meteoParams),
        fetchCapacity(code ? { regionCode: code } : {}),
      ])
      // Same stale-response guard as loadData — capacity has no date range
      // of its own, but météo does, so check against it here too.
      if (start !== latestRangeRef.current.start || end !== latestRangeRef.current.end) return
      setMeteoData(meteoRes.status === 'fulfilled' ? (meteoRes.value?.data || []) : [])
      setCapacityData(capacityRes.status === 'fulfilled' ? (capacityRes.value?.data || []) : [])
    } finally {
      setDrillLoading(false)
    }
  }, [])

  // Initial load: fetch all regions without filter (choropleth view).
  // These three are independent of each other's *results* (loadData/
  // loadDrillData don't need the regions list to run) — only firing them
  // sequentially was serializing three separate network round-trips for no
  // reason, so run them concurrently instead.
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      const [regsResult] = await Promise.all([
        fetchRegions().catch(() => []),
        loadData('', startDate, endDate, true),
        loadDrillData('', startDate, endDate),
      ])
      if (!cancelled) {
        setRegions(regsResult)
        setLoading(false)
      }
    })()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadData])

  // Negative-price calendar: fetched once, whole history
  useEffect(() => {
    let cancelled = false
    fetchCurtailmentCalendar()
      .then(result => {
        if (cancelled) return
        setCalendarDays(result.days || [])
        setCalendarRange(result.range || null)
        setCalendarStats(result.stats || null)
      })
      .catch(() => {})
      .finally(() => { if (!cancelled) setCalendarLoading(false) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchCurtailmentRisk()
      .then(result => { if (!cancelled) setCurtailmentRiskData(result.data || []) })
      .catch(() => { if (!cancelled) setCurtailmentRiskData([]) })
    return () => { cancelled = true }
  }, [])

  // Maintenance events — fetched once, whole history (Capacité tab)
  useEffect(() => {
    let cancelled = false
    fetchMaintenance({ limit: 100 })
      .then(result => { if (!cancelled) setMaintenanceEvents(result.data || []) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setMaintenanceLoading(false) })
    return () => { cancelled = true }
  }, [])

  // Day-ahead spot price — national, refetched when the shared date range
  // changes (same range as production/météo; independent of region since
  // price has no region dimension).
  useEffect(() => {
    let cancelled = false
    setPriceLoading(true)
    fetchMarketPrice({ startDate, endDate })
      .then(result => { if (!cancelled) setMarketPriceData(result.data || []) })
      .catch(() => { if (!cancelled) setMarketPriceData([]) })
      .finally(() => { if (!cancelled) setPriceLoading(false) })
    return () => { cancelled = true }
  }, [startDate, endDate])

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
    latestRangeRef.current = { start: newStart, end: newEnd }
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

  // Compute per-region totals + carbon intensity for choropleth (latest point per region)
  const { regionTotals, regionConsommation, regionCarbon, regionSources } = useMemo(() => {
    const latest = {}
    for (const r of globalData) {
      if (!latest[r.code_insee] || r.timestamp > latest[r.code_insee].timestamp) {
        latest[r.code_insee] = r
      }
    }
    const totals = {}
    const conso  = {}
    const carbon = {}
    const sources = {}
    for (const [code, rec] of Object.entries(latest)) {
      totals[code] = Object.values(rec.sources).reduce((s, v) => s + (v > 0 ? v : 0), 0)
      if (rec.consommation_mw != null) conso[code] = rec.consommation_mw
      carbon[code] = computeCarbonIntensity(rec.sources || {})
      sources[code] = rec.sources || {}
    }
    return { regionTotals: totals, regionConsommation: conso, regionCarbon: carbon, regionSources: sources }
  }, [globalData])

  // Curtailment risk by region (%) — the map's default mode, the app's
  // actual point: which regions drive curtailment.
  const regionCurtailmentRisk = useMemo(() => {
    const out = {}
    for (const row of curtailmentRiskData) out[row.code_insee] = row.share_pct
    return out
  }, [curtailmentRiskData])

  // Aggregated data for charts (sum/average across all regions when no region selected)
  const aggregatedProdData = useMemo(
    () => selectedRegion ? productionData : aggregateByTimestamp(globalData),
    [selectedRegion, productionData, globalData]
  )
  const aggregatedMeteoData = useMemo(
    () => selectedRegion ? meteoData : aggregateMeteoByTimestamp(meteoData),
    [selectedRegion, meteoData]
  )

  // Derive KPIs from current data (region-specific or global).
  // Global view must use the aggregated (summed-across-regions) series, not
  // raw globalData — that's per-region rows, so its "last point" would be a
  // single arbitrary region's MW, not France's total.
  const displayData = selectedRegion ? productionData : aggregatedProdData
  const lastSources = displayData.length
    ? (displayData[displayData.length - 1].sources || {})
    : {}
  const totalMw = computeTotalMw(displayData)
  const productionSparkData = useMemo(() =>
    aggregatedProdData.slice(-96).map(r => ({
      t: r.timestamp,
      v: Object.values(r.sources || {}).reduce((s, v) => s + (v > 0 ? v : 0), 0),
    })),
    [aggregatedProdData]
  )
  const consommationSparkData = useMemo(() =>
    aggregatedProdData.slice(-96).filter(r => r.consommation_mw != null).map(r => ({
      t: r.timestamp,
      v: r.consommation_mw,
    })),
    [aggregatedProdData]
  )
  // Équilibre prod/conso sparkline — both raw lines (not the delta), the
  // small line chart the KPI card shows instead of a full chart taking up
  // chart real estate; the headline number stays the delta.
  const soldeSparkData = useMemo(() =>
    aggregatedProdData.slice(-96).filter(r => r.consommation_mw != null).map(r => ({
      t: r.timestamp,
      v: Object.values(r.sources || {}).reduce((s, v) => s + (v > 0 ? v : 0), 0),
      v2: r.consommation_mw,
    })),
    [aggregatedProdData]
  )
  // Capacity factor (bullet chart) — average production vs installed capacity, per source
  const avgProductionBySource = useMemo(() => averageBySource(aggregatedProdData), [aggregatedProdData])
  const capacityBySource = useMemo(() => latestCapacityBySource(capacityData), [capacityData])

  // Enrich maintenance events with a region, matched against the units registry by name.
  const maintenanceEventsWithRegion = useMemo(() => {
    if (!allUnits.length) return maintenanceEvents
    return maintenanceEvents.map(evt => {
      const token = normalizeUnitName(evt.unit_name)
      const match = allUnits.find(u => { const n = normalizeUnitName(u.name); return token && (n.includes(token) || token.includes(n)) })
      return { ...evt, region: match?.region || evt.region }
    })
  }, [maintenanceEvents, allUnits])

  const maintenanceEventCount = maintenanceEvents.length
  const maintenanceTotalMw = useMemo(
    () => maintenanceEvents.reduce((s, e) => s + (e.unavailable_mw || 0), 0),
    [maintenanceEvents]
  )

  const selectedRegionName = regions.find(r => r.code_insee === selectedRegion)?.region
  const latestConsommation = consommationSparkData.length ? consommationSparkData[consommationSparkData.length - 1].v : null
  const soldeMw = latestConsommation != null ? totalMw - latestConsommation : null

  // Capacité tab: 3rd/4th chiffres
  const avgUtilisationPct = useMemo(() => {
    const keys = Object.keys(capacityBySource).filter(k => capacityBySource[k] > 0)
    if (!keys.length) return null
    const pcts = keys.map(k => Math.min(1, (avgProductionBySource[k] || 0) / capacityBySource[k]))
    return Math.round((pcts.reduce((s, v) => s + v, 0) / pcts.length) * 100)
  }, [capacityBySource, avgProductionBySource])
  const totalCapacityMw = useMemo(
    () => Object.values(capacityBySource).reduce((s, v) => s + v, 0),
    [capacityBySource]
  )


  // Prix tab: 2nd chiffre — average spot price over the selected period
  const avgPriceEurMwh = useMemo(() => {
    const vals = marketPriceData.map(d => d.price_eur_mwh).filter(v => v != null)
    if (!vals.length) return null
    return Math.round((vals.reduce((s, v) => s + v, 0) / vals.length) * 100) / 100
  }, [marketPriceData])

  const [activeTab, setActiveTab] = useState('production')

  // recharts' ResponsiveContainer measures its parent once on mount, before the
  // CSS grid (pbi-layout) has finished sizing that parent — charts render at
  // 0-height until something fires a real window resize. Switching tabs remounts
  // the newly-visible branch into the same trap, so nudge it every time.
  useEffect(() => {
    const id = setTimeout(() => window.dispatchEvent(new Event('resize')), 60)
    return () => clearTimeout(id)
  }, [activeTab])

  const TAB_ICONS = {
    production: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M13 2 4 14h6l-1 8 9-12h-6l1-8Z" />
      </svg>
    ),
    prixnegatifs: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="3" width="4.5" height="4.5" rx="1" /><rect x="9.75" y="3" width="4.5" height="4.5" rx="1" />
        <rect x="16.5" y="3" width="4.5" height="4.5" rx="1" /><rect x="3" y="9.75" width="4.5" height="4.5" rx="1" />
        <rect x="9.75" y="9.75" width="4.5" height="4.5" rx="1" fill="currentColor" />
        <rect x="3" y="16.5" width="4.5" height="4.5" rx="1" />
      </svg>
    ),
    capacite: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="7" width="16" height="10" rx="1.5" /><path d="M19 10v4M6.5 10v4M11 10v4" />
      </svg>
    ),
  }
  const TABS = [
    { id: 'production',    label: 'Production' },
    { id: 'prixnegatifs',  label: 'Prix' },
    { id: 'capacite',      label: 'Capacité' },
  ]

  // Période / région / màj — colonne centrale, empilée verticalement, identique sur tous les onglets.
  // buildControlsColumn(extra) accepts extra tab-specific content to render above the shared
  // controls — never nest two .pbi-layout__controls-col.
  const buildControlsColumn = (extra = null) => (
    <div className="pbi-layout__controls-col">
      {extra}
      <div className="controls-line">
        <div className="controls-block">
          <span className="selector-label">Période</span>
          <div className="date-bar" data-testid="date-range">
            <input id="date-start" type="date" className="selector-input date-bar__input"
              value={startDate} max={endDate} aria-label="Date de début" data-testid="date-start"
              onChange={e => { setStartDate(e.target.value); handleDateChange(e.target.value, endDate) }} />
            <span className="selector-label" aria-hidden="true">→</span>
            <input id="date-end" type="date" className="selector-input date-bar__input"
              value={endDate} min={startDate} max={isoDate(0)} aria-label="Date de fin" data-testid="date-end"
              onChange={e => { setEndDate(e.target.value); handleDateChange(startDate, e.target.value) }} />
            <div className="date-bar__presets">
              {/* 3m matches actual production data retention (~3 months) —
                  6m used to return a range the backend couldn't fill. */}
              {[{ label: '24h', days: -1 }, { label: '7j', days: -7 }, { label: '30j', days: -30 }, { label: '3m', days: -91 }].map(({ label, days }) => (
                <button key={label} onClick={() => {
                  const s = isoDate(days); const e = isoDate(0)
                  setStartDate(s); setEndDate(e); handleDateChange(s, e)
                }}>{label}</button>
              ))}
            </div>
          </div>
        </div>

        <div className="controls-region-status">
          <RegionSelector regions={regions} selected={selectedRegion} onChange={handleRegionChange} loading={loading} />
          <div className="controls-block controls-block--status">
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
      </div>
    </div>
  )

  return (
    <main id="main-content" className="app-main">

      {/* Content fills whatever height remains below the tabs —
          this is the only piece allowed to scroll, and only if it has to. */}
      <div className="dashboard-content">
        {error && (
          <div className="glass-card chart-card chart-error" data-testid="app-error">
            <p>Erreur : {error}</p>
          </div>
        )}

        {/* ── Production & consommation : le surplus (curtailment) | sélecteur + carte risque ── */}
        {activeTab === 'production' && !error && (
          <div className="pbi-layout">
            <div className="pbi-layout__left pbi-layout__left--no-kpi">
              <MeteoChart
                data={aggregatedMeteoData}
                region={selectedRegionName}
                loading={drillLoading}
              />
              <HistoryChart
                data={aggregatedProdData}
                region={selectedRegionName || 'France'}
                loading={loading || refreshing}
              />
            </div>
            <div className="pbi-layout__right">
              {buildControlsColumn()}
              <div className="pbi-layout__map-wrap">
                <FranceMap
                  regions={regions}
                  regionTotals={regionTotals}
                  regionConsommation={regionConsommation}
                  regionSources={regionSources}
                  regionCurtailmentRisk={regionCurtailmentRisk}
                  mixSources={lastSources}
                  showMixRibbon
                  selectedCode={selectedRegion}
                  onSelect={handleRegionChange}
                  loading={loading}
                  mode="dominant"
                  availableModes={['dominant']}
                />
              </div>
            </div>
          </div>
        )}

        {/* ── Prix : prix spot + calendrier | sélecteur + carte export/import + 2 chiffres ── */}
        {activeTab === 'prixnegatifs' && !error && (
          <div className="pbi-layout">
            <div className="pbi-layout__left pbi-layout__left--no-kpi">
              <PriceTrendChart data={marketPriceData} loading={priceLoading} />
              {/* hideStats=false — its own built-in stats (heures à prix
                  négatif + record) are literally "fréquence et intensité",
                  no need to duplicate them in a KPI row above too. */}
              <CurtailmentCalendar
                days={calendarDays}
                range={calendarRange}
                stats={calendarStats}
                loading={calendarLoading || !calendarStats}
                compact
              />
            </div>
            <div className="pbi-layout__right">
              <div className="pbi-layout__kpi-row pbi-layout__kpi-row--compact">
                <KPICard
                  title="Heures à prix négatif"
                  explain="Total d'heures cumulées à prix négatif sur tout l'historique disponible."
                  value={calendarStats?.total_hours ?? '—'} unit="h"
                  sublabel={calendarRange?.start ? `Depuis le ${calendarRange.start}` : undefined}
                  loading={calendarLoading || !calendarStats}
                />
                <KPICard
                  title="Prix moyen"
                  explain="Prix spot day-ahead moyen sur la période sélectionnée."
                  value={avgPriceEurMwh ?? '—'} unit="€/MWh"
                  loading={priceLoading}
                />
              </div>
              {buildControlsColumn()}
              <div className="pbi-layout__map-wrap">
                <FranceMap
                  regions={regions}
                  regionTotals={regionTotals}
                  regionConsommation={regionConsommation}
                  regionCarbon={regionCarbon}
                  selectedCode={selectedRegion}
                  onSelect={handleRegionChange}
                  loading={loading}
                  mode="balance"
                  availableModes={['balance']}
                />
              </div>
            </div>
          </div>
        )}

        {/* ── Capacité : taux d'utilisation + événements | sélecteur + carte maintenance + 2 chiffres ── */}
        {activeTab === 'capacite' && !error && (
          <div className="pbi-layout">
            <div className="pbi-layout__left pbi-layout__left--no-kpi">
              <CapacityFactorChart
                capacityBySource={capacityBySource}
                productionBySource={avgProductionBySource}
                loading={drillLoading}
              />
              <section className="glass-card chart-card" data-testid="maintenance-list">
              <h2 className="chart-title" title="Événements d'indisponibilité de production (planifiés ou non) publiés par ENTSO-E, en cours ou à venir.">Événements de maintenance en cours</h2>
              {maintenanceLoading ? (
                <div className="skeleton" style={{ height: 260 }} />
              ) : maintenanceEventsWithRegion.length === 0 ? (
                <div className="empty-state">
                  <p className="empty-state__title">Aucun événement</p>
                </div>
              ) : (
                <div style={{ overflowY: 'auto', maxHeight: 320 }}>
                  {maintenanceEventsWithRegion.slice(0, 30).map(evt => (
                    <div key={evt.event_id} style={{
                      display: 'flex', justifyContent: 'space-between', gap: 10,
                      padding: '8px 0', borderBottom: '1px solid var(--color-border)', fontSize: '0.8rem',
                    }}>
                      <span style={{ color: 'var(--color-text)' }}>{evt.unit_name || '—'}</span>
                      <span style={{ color: 'var(--color-text-muted)' }}>{evt.region || '—'}</span>
                      <span style={{ color: 'var(--color-text-muted)' }}>{evt.event_type}</span>
                      <span style={{ color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                        {evt.unavailable_mw ? `${Math.round(evt.unavailable_mw)} MW` : '—'}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              </section>
            </div>
            <div className="pbi-layout__right">
              <div className="pbi-layout__kpi-row pbi-layout__kpi-row--compact">
                <KPICard
                  title="Événements en cours"
                  explain="Nombre total d'événements de maintenance publiés par ENTSO-E."
                  value={maintenanceEventCount} loading={maintenanceLoading}
                />
                <KPICard
                  title="MW indisponibles"
                  explain="Somme des puissances concernées par un événement de maintenance."
                  value={Math.round(maintenanceTotalMw).toLocaleString('fr-FR')} unit="MW"
                  loading={maintenanceLoading}
                />
              </div>
              {buildControlsColumn()}
              <div className="pbi-layout__map-wrap">
                <MaintenanceMap maintenanceEvents={maintenanceEvents} loading={maintenanceLoading} />
              </div>
            </div>
          </div>
        )}

      </div>

      {/* ── Onglets thématiques — bande latérale droite ── */}
      <nav className="dashboard-side-tabs" role="tablist" aria-label="Sections du dashboard">
        {TABS.map(t => (
          <button
            key={t.id}
            role="tab"
            aria-selected={activeTab === t.id}
            className={`footer-tab${activeTab === t.id ? ' footer-tab--active' : ''}`}
            onClick={() => setActiveTab(t.id)}
          >
            {TAB_ICONS[t.id]}
            {t.label}
          </button>
        ))}
      </nav>

    </main>
  )
}
