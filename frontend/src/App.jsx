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
import { useState, useEffect, useCallback, useMemo, lazy, Suspense } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from './context/AuthContext.jsx'
import { logout as apiLogout, fetchProduction, fetchRegions, fetchAlerts, triggerPipeline, fetchMeteo } from './services/api.js'
import { KPICard } from './components/KPICard.jsx'
import { FranceMap } from './components/FranceMap.jsx'
import { computeCarbonIntensity } from './components/CarbonGauge.jsx'
import { AlertBanner } from './components/AlertBanner.jsx'
import { AlertHistory } from './components/AlertHistory.jsx'
import { RegionSelector } from './components/RegionSelector.jsx'

// Lazy-load recharts-based components to avoid circular-dep TDZ crash in prod bundle
const CarbonBadge   = lazy(() => import('./components/CarbonBadge.jsx').then(m => ({ default: m.CarbonBadge })))
const ProdConsChart = lazy(() => import('./components/ProdConsChart.jsx').then(m => ({ default: m.ProdConsChart })))
const MeteoChart    = lazy(() => import('./components/MeteoChart.jsx').then(m => ({ default: m.MeteoChart })))

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

/** Aggregate multi-region data by timestamp (sum sources, sum conso). */
function aggregateByTimestamp(data) {
  const map = new Map()
  for (const r of data) {
    const ts = r.timestamp
    if (!map.has(ts)) map.set(ts, { timestamp: ts, sources: {}, consommation_mw: null })
    const agg = map.get(ts)
    for (const [src, mw] of Object.entries(r.sources || {})) {
      if (typeof mw === 'number' && mw > 0) agg.sources[src] = (agg.sources[src] || 0) + mw
    }
    if (r.consommation_mw != null) agg.consommation_mw = (agg.consommation_mw || 0) + r.consommation_mw
  }
  return Array.from(map.values()).sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1))
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
      timestamp:       r.timestamp,
      temperature_c:   r.n ? Math.round((r.temp  / r.n) * 10) / 10 : null,
      wind_speed_10m:  r.n ? Math.round((r.wind  / r.n) * 10) / 10 : null,
      cloudcover_pct:  r.n ? Math.round( r.cloud / r.n)            : null,
    }))
}

/** Inline colored chips showing current MW per source. */
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

export default function App() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const handleLogout = useCallback(async () => {
    await apiLogout()
    logout()
    navigate('/login')
  }, [logout, navigate])

  const [theme, setTheme] = useState(
    () => window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  )
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
  const [pipelineRunning, setPipelineRunning] = useState(false)
  const [pipelineError, setPipelineError] = useState(null)

  // Date range filter (default: last 7 days)
  const [startDate, setStartDate] = useState(isoDate(-7))
  const [endDate, setEndDate] = useState(isoDate(0))

  // Meteo data (France or region)
  const [meteoData, setMeteoData] = useState([])
  const [drillLoading, setDrillLoading] = useState(false)

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
        await Promise.all([
          loadData('', startDate, endDate, true),
          loadAlerts(''),
          loadDrillData('', startDate, endDate),
        ])
        setLoading(false)
      }
    })()
    return () => { cancelled = true }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadData, loadAlerts, loadDrillData])

  // Load meteo (+ capacity when region selected)
  const loadDrillData = useCallback(async (code, start, end) => {
    setDrillLoading(true)
    try {
      const meteoParams = code
        ? { regionCode: code, startDate: start, endDate: end }
        : { startDate: start, endDate: end }
      const [meteoRes] = await Promise.allSettled([fetchMeteo(meteoParams)])
      setMeteoData(meteoRes.status === 'fulfilled' ? (meteoRes.value?.data || []) : [])
    } finally {
      setDrillLoading(false)
    }
  }, [])

  // Region change: drill down into a specific region (or reset to global view)
  const handleRegionChange = useCallback(async (code) => {
    setSelectedRegion(code)
    setRefreshing(true)
    setDismissedAlertId(null)
    await Promise.all([
      loadData(code || '', startDate, endDate, !code),
      loadAlerts(code || ''),
      loadDrillData(code || '', startDate, endDate),
    ])
    setRefreshing(false)
  }, [loadData, loadAlerts, loadDrillData, startDate, endDate])

  // Date range change: reload data (preserve region selection)
  const handleDateChange = useCallback(async (newStart, newEnd) => {
    setRefreshing(true)
    await Promise.all([
      loadData(selectedRegion || '', newStart, newEnd, !selectedRegion),
      selectedRegion ? loadData('', newStart, newEnd, true) : Promise.resolve(),
      loadDrillData(selectedRegion || '', newStart, newEnd),
    ])
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

  const handlePipelineRefresh = useCallback(async () => {
    setPipelineRunning(true)
    setPipelineError(null)
    try {
      await triggerPipeline()
      setRefreshing(true)
      await Promise.all([
        loadData(selectedRegion || '', startDate, endDate, !selectedRegion),
        loadAlerts(selectedRegion || ''),
        loadDrillData(selectedRegion || '', startDate, endDate),
      ])
      setLastUpdated(new Date())
    } catch (err) {
      setPipelineError(err.message || 'Erreur pipeline')
    } finally {
      setPipelineRunning(false)
      setRefreshing(false)
    }
  }, [selectedRegion, startDate, endDate, loadData, loadAlerts, loadDrillData])

  // Story 5.2 — alert polling every 60 s (AC #1, Task 3.3)
  useEffect(() => {
    const id = setInterval(() => loadAlerts(selectedRegion), ALERT_POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [selectedRegion, loadAlerts])

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

  // Derive KPIs from current data (region-specific or global)
  const displayData = selectedRegion ? productionData : globalData
  const lastSources = displayData.length
    ? (displayData[displayData.length - 1].sources || {})
    : {}
  const totalMw = computeTotalMw(displayData)
  const carbonIntensity = computeCarbonIntensity(lastSources)

  // Sparkline data: carbon intensity per time point (last 96 points max)
  const sparkData = useMemo(() =>
    displayData.slice(-96).map(r => ({
      t: r.timestamp,
      v: computeCarbonIntensity(r.sources || {}),
    })),
    [displayData]
  )

  // Aggregated data for national view (memoized to avoid recompute on every render)
  const aggregatedProdData = useMemo(() =>
    selectedRegion ? productionData : aggregateByTimestamp(globalData),
    [selectedRegion, productionData, globalData]
  )

  const aggregatedMeteoData = useMemo(() =>
    selectedRegion ? meteoData : aggregateMeteoByTimestamp(meteoData),
    [selectedRegion, meteoData]
  )

  // Top alert to display in banner (highest severity, not dismissed)
  const severityOrder = { CRITICAL: 0, WARNING: 1, INFO: 2 }
  const topAlert = alerts
    .filter(a => a.alert_id !== dismissedAlertId)
    .sort((a, b) => (severityOrder[a.severity] ?? 9) - (severityOrder[b.severity] ?? 9))[0] ?? null

  const hasCritical = alerts.some(a => a.severity === 'CRITICAL' && a.alert_id !== dismissedAlertId)

  const selectedRegionName = regions.find(r => r.code_insee === selectedRegion)?.region

  return (
    <div className="app-layout" data-testid="app-layout">
      {/* ── Skip link — WCAG 2.4.1 ───────────────────────────────── */}
      <a href="#main-content" className="skip-link">Passer au contenu principal</a>

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
          {/* Region selector inline dans le header */}
          <RegionSelector
            regions={regions}
            selected={selectedRegion}
            onChange={handleRegionChange}
            loading={loading}
          />
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
          {pipelineError && (
            <span className="last-updated" style={{ color: 'var(--color-error, #f87171)' }} title={pipelineError}>
              Erreur pipeline
            </span>
          )}
          <button
            className="btn btn-ghost"
            onClick={handlePipelineRefresh}
            disabled={pipelineRunning}
            aria-label="Rafraîchir les données"
            data-testid="pipeline-refresh"
            title={pipelineRunning ? 'Pipeline en cours…' : 'Rafraîchir les données depuis RTE'}
          >
            {pipelineRunning ? '⏳' : '↻'}
          </button>
          <button
            className="btn btn-ghost"
            onClick={() => setTheme(t => t === 'dark' ? 'light' : 'dark')}
            aria-label="Basculer le thème"
            data-testid="theme-toggle"
          >
            {theme === 'dark' ? '☀' : '⏾'}
          </button>
          <Link to="/subscriptions" className="btn btn-ghost" title="Gérer mes alertes email">
            🔔
          </Link>
          {user && (
            <button className="btn btn-ghost" onClick={handleLogout} title={`Déconnexion (${user.email})`}>
              ⎋
            </button>
          )}
        </div>
      </header>

      {/* ── Alert banner ──────────────────────────────────────────── */}
      <AlertBanner
        alert={topAlert}
        onDismiss={() => topAlert && setDismissedAlertId(topAlert.alert_id)}
      />

      {/* sidebar supprimée — contenu déplacé dans app-main */}
      {false && <aside className="app-sidebar">
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

      </aside>}

      {/* ── Main ──────────────────────────────────────────────────── */}
      <main id="main-content" className="app-main">

        {/* Date range bar */}
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

        {/* ── KPI strip ────────────────────────────────────────── */}
        <div className="kpi-grid" data-testid="kpi-grid">
          <KPICard
            title={selectedRegionName ? `Production — ${selectedRegionName}` : 'Production France'}
            value={totalMw.toLocaleString('fr-FR')} unit="MW" loading={loading}
          />
          <Suspense fallback={<div className="glass-card kpi-card"><div className="skeleton" style={{height:88}}/></div>}>
            <CarbonBadge intensity={carbonIntensity} sparkData={sparkData} loading={loading} />
          </Suspense>
          <KPICard
            title={selectedRegion ? 'Points de données' : 'Régions actives'}
            value={selectedRegion ? productionData.length : Object.keys(regionTotals).length}
            loading={loading}
          />
          {/* Mix énergétique actuel */}
          <div className="glass-card kpi-card" style={{ gridColumn: 'span 1' }}>
            <p className="kpi-title">Mix énergétique actuel</p>
            <SourceChips sources={lastSources} />
          </div>
        </div>

        {/* ── Hero : carte + prod/conso ─────────────────────────── */}
        <div className="hero-grid">
          <FranceMap
            regions={regions}
            regionTotals={regionTotals}
            regionConsommation={regionConsommation}
            selectedCode={selectedRegion}
            onSelect={handleRegionChange}
            loading={loading}
          />
          <Suspense fallback={<div className="glass-card chart-card"><div className="skeleton" style={{height:320}}/></div>}>
            <ProdConsChart
              data={aggregatedProdData}
              region={selectedRegionName}
              loading={loading || refreshing}
            />
          </Suspense>
        </div>

        {/* ── Météo (France ou région) ──────────────────────────── */}
        {error ? (
          <div className="glass-card chart-card chart-error" data-testid="app-error">
            <p>Erreur : {error}</p>
          </div>
        ) : (
          <Suspense fallback={<div className="glass-card chart-card"><div className="skeleton" style={{height:260}}/></div>}>
            <MeteoChart
              data={aggregatedMeteoData}
              region={selectedRegionName || 'France'}
              loading={drillLoading}
            />
          </Suspense>
        )}

        {/* ── Historique alertes ────────────────────────────────── */}
        <AlertHistory alerts={alerts} loading={alertsLoading} />

      </main>
    </div>
  )
}
