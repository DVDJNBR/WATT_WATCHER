/**
 * AlertHistory — Story 5.2, Task 3.2
 *
 * List view of recent alerts with timestamps, severity badges,
 * and region labels. Collapses when empty.
 * AC #1, #2: Shows audit trail of alerts.
 */

const SEVERITY_BADGE = {
  CRITICAL: { bg: 'var(--alert-critical)', label: 'CRITIQUE' },
  WARNING:  { bg: 'var(--alert-warning)',  label: 'ATTENTION' },
  INFO:     { bg: 'var(--alert-info)',      label: 'INFO' },
}

function formatTs(isoString) {
  if (!isoString) return '—'
  try {
    return new Date(isoString).toLocaleString('fr-FR', {
      day: '2-digit', month: '2-digit', year: 'numeric',
      hour: '2-digit', minute: '2-digit',
    })
  } catch {
    return isoString
  }
}

/**
 * @param {{ alerts: object[], loading: boolean }} props
 */
export function AlertHistory({ alerts = [], loading = false }) {
  if (loading) {
    return (
      <div className="alert-history">
        <h3 className="alert-history__title">Historique des alertes</h3>
        <p className="alert-history__empty">Chargement…</p>
      </div>
    )
  }

  if (!alerts.length) {
    return (
      <div className="alert-history">
        <h3 className="alert-history__title">Historique des alertes</h3>
        <p className="alert-history__empty">Aucune alerte récente ✓</p>
      </div>
    )
  }

  return (
    <div className="alert-history">
      <h3 className="alert-history__title">
        Historique des alertes
        <span className="alert-history__count">{alerts.length}</span>
      </h3>
      <ul className="alert-history__list">
        {alerts.map((alert) => {
          const badge = SEVERITY_BADGE[alert.severity] ?? SEVERITY_BADGE.INFO
          return (
            <li key={alert.alert_id} className="alert-history__item">
              <span
                className="alert-history__badge"
                style={{ background: badge.bg }}
              >
                {badge.label}
              </span>
              <div className="alert-history__body">
                <span className="alert-history__region">
                  {alert.region_label || alert.region}
                </span>
                <span className="alert-history__details">{alert.details}</span>
                <time className="alert-history__time" dateTime={alert.timestamp}>
                  {formatTs(alert.timestamp)}
                </time>
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
