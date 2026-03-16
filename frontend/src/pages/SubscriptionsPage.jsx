/**
 * SubscriptionsPage — manage alert subscriptions per region.
 *
 * Shows a grid of French regions; each has two toggles:
 *   • Sous-production (prod < conso)
 *   • Sur-production  (prod > conso)
 *
 * Saves via PUT /v1/subscriptions on any change.
 */
import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext.jsx'
import { fetchRegions, fetchSubscriptions, updateSubscriptions, logout as apiLogout } from '../services/api.js'

const ALERT_TYPES = [
  { key: 'sous_production', label: 'Sous-production', color: '#f59e0b' },
  { key: 'sur_production',  label: 'Sur-production',  color: '#ef4444' },
]

export default function SubscriptionsPage() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()

  const [regions, setRegions]   = useState([])
  const [subs,    setSubs]      = useState({})   // { [code_insee]: { sous_production: bool, sur_production: bool } }
  const [loading, setLoading]   = useState(true)
  const [saving,  setSaving]    = useState(false)
  const [saved,   setSaved]     = useState(false)
  const [error,   setError]     = useState(null)

  // Load regions + subscriptions
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [regs, subsResult] = await Promise.all([fetchRegions(), fetchSubscriptions()])
        if (cancelled) return
        setRegions(regs)

        // Build subs map from API response
        const map = {}
        for (const r of regs) {
          map[r.code_insee] = { sous_production: false, sur_production: false }
        }
        for (const s of (subsResult.subscriptions || [])) {
          if (map[s.region_code]) {
            map[s.region_code][s.alert_type] = s.active !== false
          }
        }
        setSubs(map)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Erreur de chargement')
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const toggle = useCallback((code, alertType) => {
    setSubs(prev => ({
      ...prev,
      [code]: { ...prev[code], [alertType]: !prev[code]?.[alertType] },
    }))
  }, [])

  const handleSave = useCallback(async () => {
    setSaving(true)
    setSaved(false)
    setError(null)
    try {
      const subscriptions = []
      for (const [region_code, types] of Object.entries(subs)) {
        for (const alert_type of Object.keys(types)) {
          subscriptions.push({ region_code, alert_type, active: types[alert_type] })
        }
      }
      await updateSubscriptions(subscriptions)
      setSaved(true)
      setTimeout(() => setSaved(false), 2500)
    } catch (err) {
      setError(err.message || 'Erreur lors de la sauvegarde')
    } finally {
      setSaving(false)
    }
  }, [subs])

  const handleLogout = useCallback(async () => {
    await apiLogout()
    logout()
    navigate('/login')
  }, [logout, navigate])

  const activeCount = Object.values(subs).reduce((n, t) =>
    n + Object.values(t).filter(Boolean).length, 0
  )

  return (
    <div className="app-layout" data-testid="subscriptions-page">
      <header className="app-header">
        <span className="logo" aria-label="WATT WATCHER">⚡ WATT WATCHER</span>
        <div className="header-actions">
          <Link to="/" className="btn btn-ghost">← Dashboard</Link>
          <span className="last-updated">{user?.email}</span>
          <button className="btn btn-ghost" onClick={handleLogout}>Déconnexion</button>
        </div>
      </header>

      <main className="app-main" style={{ maxWidth: 860, margin: '0 auto' }}>
        <div style={{ marginBottom: 24 }}>
          <h1 className="chart-title">Mes abonnements aux alertes</h1>
          <p className="map-hint">
            Recevez un email quand une région bascule en déséquilibre.
            Maximum 1 email par région et par type d'événement par jour.
          </p>
        </div>

        {error && <div className="auth-error" role="alert">{error}</div>}

        {loading ? (
          <div className="glass-card" style={{ padding: 32 }}>
            <div className="skeleton" style={{ height: 300 }} />
          </div>
        ) : (
          <>
            <div className="subs-grid">
              {regions.map(r => (
                <div key={r.code_insee} className="subs-card glass-card">
                  <p className="subs-card__name">{r.region}</p>
                  <div className="subs-card__toggles">
                    {ALERT_TYPES.map(({ key, label, color }) => {
                      const active = subs[r.code_insee]?.[key] ?? false
                      return (
                        <button
                          key={key}
                          className={`subs-toggle ${active ? 'subs-toggle--on' : ''}`}
                          style={active ? { borderColor: color, color } : {}}
                          onClick={() => toggle(r.code_insee, key)}
                          aria-pressed={active}
                          title={active ? `Désactiver alerte ${label}` : `Activer alerte ${label}`}
                        >
                          <span className="subs-toggle__dot" style={active ? { background: color } : {}} />
                          {label}
                        </button>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>

            <div className="subs-footer">
              <span className="map-hint">
                {activeCount > 0
                  ? `${activeCount} alerte${activeCount > 1 ? 's' : ''} active${activeCount > 1 ? 's' : ''}`
                  : 'Aucune alerte active'}
              </span>
              <button
                className="btn btn-primary"
                onClick={handleSave}
                disabled={saving}
                data-testid="save-subscriptions"
              >
                {saving ? 'Enregistrement…' : saved ? 'Enregistré ✓' : 'Enregistrer'}
              </button>
            </div>
          </>
        )}
      </main>
    </div>
  )
}
