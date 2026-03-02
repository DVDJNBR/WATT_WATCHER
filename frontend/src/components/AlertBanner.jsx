/**
 * AlertBanner — Story 5.2, Task 3.1
 *
 * Dismissible banner for the highest-priority active alert.
 * AC #1: Color-coded — red for CRITICAL, orange for WARNING.
 * AC #3: Pulsing icon when severity is CRITICAL.
 */
import { useState } from 'react'

const SEVERITY_CONFIG = {
  CRITICAL: { color: 'var(--alert-critical)', label: '🔴 Alerte critique', pulse: true },
  WARNING:  { color: 'var(--alert-warning)',  label: '🟠 Avertissement',   pulse: false },
  INFO:     { color: 'var(--alert-info)',      label: 'ℹ️ Information',     pulse: false },
}

/**
 * @param {{ alert: object|null, onDismiss: () => void }} props
 */
export function AlertBanner({ alert, onDismiss }) {
  const [dismissed, setDismissed] = useState(false)

  if (!alert || dismissed) return null

  const config = SEVERITY_CONFIG[alert.severity] ?? SEVERITY_CONFIG.INFO
  const regionLabel = alert.region_label || alert.region || '?'

  function handleDismiss() {
    setDismissed(true)
    onDismiss?.()
  }

  return (
    <div
      className="alert-banner"
      data-severity={alert.severity}
      role="alert"
      aria-live="assertive"
      style={{ borderLeftColor: config.color }}
    >
      <span className={`alert-icon${config.pulse ? ' alert-icon--pulse' : ''}`} aria-hidden="true">
        ⚡
      </span>
      <div className="alert-content">
        <strong className="alert-label" style={{ color: config.color }}>
          {config.label}
        </strong>
        <span className="alert-region">{regionLabel}</span>
        <span className="alert-details">{alert.details}</span>
      </div>
      <button
        className="alert-dismiss"
        onClick={handleDismiss}
        aria-label="Fermer l'alerte"
        title="Fermer"
      >
        ×
      </button>
    </div>
  )
}
