/**
 * KPICard — Story 5.1, Task 4.3
 *
 * Glassmorphism card for key performance indicators.
 * AC #3: Glassmorphism + dark-mode design.
 */

/** @param {{ title: string, value: string|number, unit?: string, trend?: 'up'|'down'|'flat', loading?: boolean }} props */
export function KPICard({ title, value, unit = '', trend, loading = false }) {
  const trendIcon = trend === 'up' ? '↑' : trend === 'down' ? '↓' : '—'
  const trendClass = trend === 'up' ? 'badge-success' : trend === 'down' ? 'badge-warn' : ''

  return (
    <article className="glass-card kpi-card" data-testid="kpi-card">
      <header className="kpi-header">
        <span className="kpi-title">{title}</span>
        {trend !== undefined && (
          <span className={`badge ${trendClass}`}>{trendIcon}</span>
        )}
      </header>

      {loading ? (
        <div className="skeleton" style={{ height: '2rem', marginTop: '8px' }} data-testid="kpi-skeleton" />
      ) : (
        <p className="kpi-value" data-testid="kpi-value" aria-live="polite">
          {value}
          {unit && <span className="kpi-unit"> {unit}</span>}
        </p>
      )}
    </article>
  )
}
