/**
 * App — Story 5.1, Tasks 2.1, 2.5, 3.3, 4.1, 4.4
 *      Story 5.2, Tasks 3.3, 3.4
 *
 * Main dashboard layout: header + sidebar + main charts area.
 * AC #1: Fetches real-time data and displays interactive charts.
 * AC #2: Region selection updates all charts.
 * AC #3: Responsive, dark/light theme, glassmorphism design.
 * AC #4: MSAL.js SSO authentication via api.js.
 * Story 5.2 AC #1: Alert polling every 60 s + AlertBanner + AlertHistory.
 * Story 5.2 AC #3: Pulsing icon in header when active alerts exist.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import { KPICard } from './components/KPICard.jsx'
import { FranceMap } from './components/FranceMap.jsx'
import { HistoryChart } from './components/HistoryChart.jsx'
import { CarbonGauge, computeCarbonIntensity } from './components/CarbonGauge.jsx'
import { AlertBanner } from './components/AlertBanner.jsx'
import { AlertHistory } from './components/AlertHistory.jsx'
import { fetchProduction, fetchRegions, fetchAlerts } from './services/api.js'

const REFRESH_INTERVAL_MS = 15 * 60 * 1000  // 15 minutes
const ALERT_POLL_INTERVAL_MS = 60 * 1000    // 60 seconds

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

export default function App() {
  const [theme, setTheme] = useState('dark')
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

  // Story 5.2 — alert state
  const [alerts, setAlerts] = useState([])
  const [alertsLoading, setAlertsLoading] = useState(false)
  const [dismissedAlertId, setDismissedAlertId] = useState(null)

  // Apply theme to root element (AC #3)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

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

  // Story 5.2 — load alerts (AC #1: poll every 60 s)
  const loadAlerts = useCallback(async (regionCode) => {
    setAlertsLoading(true)
    try {
      const result = await fetchAlerts({ regionCode: regionCode || undefined })
      setAlerts(result.alerts || [])
    } catch {
      // Non-blocking — alert failures don't break the dashboard
    } finally {
      setAlertsLoading(false)
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
        await loadAlerts('')
        setLoading(false)
      }
    })()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadData, loadAlerts])

  // Region change: drill down into a specific region (or reset to global view)
  const handleRegionChange = useCallback(async (code) => {
    setSelectedRegion(code)
    setRefreshing(true)
    setDismissedAlertId(null)
    if (code) {
      // Drill-down: load selected region only
      await Promise.all([loadData(code, startDate, endDate), loadAlerts(code)])
    } else {
      // Back to global view: reload all-regions data
      await Promise.all([loadData('', startDate, endDate, true), loadAlerts('')])
    }
    setRefreshing(false)
  }, [loadData, loadAlerts, startDate, endDate])

  // Date range change: reload data (preserve region selection)
  const handleDateChange = useCallback(async (newStart, newEnd) => {
    setRefreshing(true)
    if (selectedRegion) {
      // Keep choropleth up to date too
      await Promise.all([
        loadData(selectedRegion, newStart, newEnd),
        loadData('', newStart, newEnd, true).then(() => {}),
      ])
    } else {
      await loadData('', newStart, newEnd, true)
    }
    setRefreshing(false)
  }, [loadData, selectedRegion])

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

  // Story 5.2 — alert polling every 60 s (AC #1, Task 3.3)
  useEffect(() => {
    const id = setInterval(() => loadAlerts(selectedRegion), ALERT_POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [selectedRegion, loadAlerts])

  // Compute per-region total production for choropleth (latest point per region)
  const regionTotals = useMemo(() => {
    const latest = {}
    for (const r of globalData) {
      if (!latest[r.code_insee] || r.timestamp > latest[r.code_insee].timestamp) {
        latest[r.code_insee] = r
      }
    }
    const totals = {}
    for (const [code, rec] of Object.entries(latest)) {
      totals[code] = Object.values(rec.sources).reduce((s, v) => s + (v > 0 ? v : 0), 0)
    }
    return totals
  }, [globalData])

  // Derive KPIs from current data (region-specific or global)
  const displayData = selectedRegion ? productionData : globalData
  const lastSources = displayData.length
    ? (displayData[displayData.length - 1].sources || {})
    : {}
  const totalMw = computeTotalMw(displayData)
  const dominantSource = computeDominantSource(displayData)
  const carbonIntensity = computeCarbonIntensity(lastSources)

  // Top alert to display in banner (highest severity, not dismissed)
  const severityOrder = { CRITICAL: 0, WARNING: 1, INFO: 2 }
  const topAlert = alerts
    .filter(a => a.alert_id !== dismissedAlertId)
    .sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))[0] ?? null

  const hasCritical = alerts.some(a => a.severity === 'CRITICAL' && a.alert_id !== dismissedAlertId)

  const selectedRegionName = regions.find(r => r.code_insee === selectedRegion)?.region

  return (
    <div className="app-layout" data-testid="app-layout">
      {/* ── Header ────────────────────────────────────────────────── */}
      <header className="app-header">
        <span className="logo" aria-label="WATT WATCHER">
          ⚡ WATT WATCHER
          {hasCritical && (
            <span
              className="alert-pulse-dot"
              aria-label="Alertes critiques actives"
              title="Alertes critiques actives"
              data-testid="alert-pulse-dot"
            />
          )}
        </span>

        <div className="header-actions">
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
          <button
            className="btn btn-ghost"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            aria-label="Basculer le thème"
            data-testid="theme-toggle"
          >
            {theme === 'dark' ? '☀' : '⏾'}
          </button>
        </div>
      </header>

      {/* ── Alert banner (Story 5.2, Task 3.1) ───────────────────── */}
      <AlertBanner
        alert={topAlert}
        onDismiss={() => topAlert && setDismissedAlertId(topAlert.alert_id)}
      />

      {/* ── Sidebar ───────────────────────────────────────────────── */}
      <aside className="app-sidebar">
        {/* Date range picker */}
        <div className="date-range" data-testid="date-range">
          <p className="selector-label">Plage de dates</p>
          <div className="date-range__fields">
            <label className="date-range__label" htmlFor="date-start">Début</label>
            <input
              id="date-start"
              type="date"
              className="selector-input"
              value={startDate}
              max={endDate}
              onChange={e => {
                setStartDate(e.target.value)
                handleDateChange(e.target.value, endDate)
              }}
              data-testid="date-start"
            />
            <label className="date-range__label" htmlFor="date-end">Fin</label>
            <input
              id="date-end"
              type="date"
              className="selector-input"
              value={endDate}
              min={startDate}
              max={isoDate(0)}
              onChange={e => {
                setEndDate(e.target.value)
                handleDateChange(startDate, e.target.value)
              }}
              data-testid="date-end"
            />
          </div>
          <div className="date-range__presets">
            {[
              { label: '24h',   days: -1 },
              { label: '7j',    days: -7 },
              { label: '30j',   days: -30 },
            ].map(({ label, days }) => (
              <button
                key={label}
                className="btn btn-ghost btn-xs"
                onClick={() => {
                  const s = isoDate(days)
                  const e = isoDate(0)
                  setStartDate(s)
                  setEndDate(e)
                  handleDateChange(s, e)
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Story 5.2, Task 3.2 — alert history */}
        <AlertHistory alerts={alerts} loading={alertsLoading} />
      </aside>

      {/* ── Main ──────────────────────────────────────────────────── */}
      <main className="app-main">
        {/* KPI widgets — show totals for selected region or all France */}
        <div className="kpi-grid" data-testid="kpi-grid">
          <KPICard
            title={selectedRegionName ? `Production — ${selectedRegionName}` : 'Production France'}
            value={totalMw.toLocaleString('fr-FR')}
            unit="MW"
            loading={loading}
          />
          <KPICard
            title="Source dominante"
            value={dominantSource}
            loading={loading}
          />
          <KPICard
            title="Intensité carbone"
            value={carbonIntensity}
            unit="gCO₂/kWh"
            loading={loading}
          />
          <KPICard
            title={selectedRegion ? 'Points de données' : 'Régions actives'}
            value={selectedRegion ? productionData.length : Object.keys(regionTotals).length}
            loading={loading}
          />
        </div>

        {/* Choropleth map — always visible */}
        <FranceMap
          regions={regions}
          regionTotals={regionTotals}
          selectedCode={selectedRegion}
          onSelect={handleRegionChange}
          loading={loading}
        />

        {/* Drill-down: shown when a region is selected */}
        {error ? (
          <div className="glass-card chart-card chart-error" data-testid="app-error">
            <p>Erreur : {error}</p>
          </div>
        ) : selectedRegion ? (
          <div data-testid="charts-grid">
            <HistoryChart
              data={productionData}
              region={selectedRegionName}
              loading={loading || refreshing}
            />
            <div style={{ marginTop: '24px' }}>
              <CarbonGauge
                sources={lastSources}
                loading={loading}
              />
            </div>
          </div>
        ) : null}
      </main>
    </div>
  )
}
