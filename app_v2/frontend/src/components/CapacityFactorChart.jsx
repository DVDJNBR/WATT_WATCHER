/**
 * CapacityFactorChart — bullet-chart style: installed capacity (back layer)
 * vs. real production (front layer), same height, offset a few px down+right
 * for a stacked-card depth effect. One row per source, sorted by rate desc.
 */
import { useMemo } from 'react'

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
const SOURCE_LABELS = {
  nucleaire: 'Nucléaire', eolien: 'Éolien', solaire: 'Solaire', hydraulique: 'Hydraulique',
  gaz: 'Gaz', bioenergies: 'Bioénergies', charbon: 'Charbon', fioul: 'Fioul',
}

function hexToRgb(hex) {
  const h = hex.replace('#', '')
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16))
}
function mix(hex1, hex2, t) {
  const [r1, g1, b1] = hexToRgb(hex1), [r2, g2, b2] = hexToRgb(hex2)
  return `rgb(${Math.round(r1 * t + r2 * (1 - t))},${Math.round(g1 * t + g2 * (1 - t))},${Math.round(b1 * t + b2 * (1 - t))})`
}
function darken(hex, t) {
  const [r, g, b] = hexToRgb(hex)
  return `rgb(${Math.round(r * t)},${Math.round(g * t)},${Math.round(b * t)})`
}
function fmtGw(mw) {
  return (mw / 1000).toLocaleString('fr-FR', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + ' GW'
}

/**
 * @param {{ capacityBySource: Record<string, number>, productionBySource: Record<string, number>, loading?: boolean }} props
 */
export function CapacityFactorChart({ capacityBySource = {}, productionBySource = {}, loading = false }) {
  const rows = useMemo(() => {
    return Object.keys(capacityBySource)
      .filter(k => capacityBySource[k] > 0 && SOURCE_COLORS[k])
      .map(key => {
        const capacity = capacityBySource[key]
        const production = Math.min(productionBySource[key] || 0, capacity)
        const pct = capacity > 0 ? Math.round((production / capacity) * 100) : 0
        return { key, capacity, production, pct }
      })
      .sort((a, b) => b.pct - a.pct)
  }, [capacityBySource, productionBySource])

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="capacity-factor-loading">
        <h2 className="chart-title">Taux d'utilisation par source</h2>
        <div className="skeleton" style={{ height: 260 }} />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="glass-card chart-card" data-testid="capacity-factor-empty">
        <h2 className="chart-title">Taux d'utilisation par source</h2>
        <div className="empty-state">
          <p className="empty-state__title">Pas de données de capacité pour cette région</p>
          <p className="empty-state__hint">La capacité installée est renseignée par région — sélectionnez-en une.</p>
        </div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="capacity-factor">
      <h2 className="chart-title">Taux d'utilisation par source</h2>
      <div style={{ display: 'flex', gap: 22, marginBottom: 14, fontSize: '0.76rem', color: 'var(--color-text-muted)' }}>
        <span><span style={{ display: 'inline-block', width: 22, height: 10, background: '#2a2620', borderRadius: 4, marginRight: 6, verticalAlign: 'middle' }} />Capacité installée</span>
        <span><span style={{ display: 'inline-block', width: 22, height: 10, background: '#8a8378', borderRadius: 4, marginRight: 6, verticalAlign: 'middle' }} />Production réelle</span>
      </div>
      <div>
        {rows.map(({ key, capacity, production, pct }) => {
          const color = SOURCE_COLORS[key]
          const track = mix(color, '#171512', 0.3)
          const edge = darken(color, 0.55)
          const narrow = pct < 16
          return (
            <div key={key} style={{ display: 'grid', gridTemplateColumns: '108px 1fr', alignItems: 'center', gap: 14, marginBottom: 14 }}>
              <span style={{ fontSize: '0.78rem', color: 'var(--color-text-muted)', textAlign: 'right' }}>{SOURCE_LABELS[key]}</span>
              <div style={{ position: 'relative', height: 26 }}>
                <div style={{ position: 'absolute', top: 6, left: 6, right: 0, height: 20, borderRadius: 5, background: track, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 9 }}>
                  <span style={{ fontSize: '0.68rem', color: '#6b6863' }}>{fmtGw(capacity)}</span>
                </div>
                <div style={{ position: 'absolute', top: 0, left: 0, height: 20, width: `${pct}%`, minWidth: 6, borderRadius: 5, background: color, border: `1px solid ${edge}`, boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 9 }}>
                  {!narrow && <span style={{ fontSize: '0.68rem', fontWeight: 600, color: '#17130f', whiteSpace: 'nowrap' }}>{fmtGw(production)}</span>}
                </div>
                {narrow && (
                  <span style={{ position: 'absolute', top: 0, bottom: 0, left: `calc(${pct}% + 10px)`, display: 'flex', alignItems: 'center', fontSize: '0.68rem', color: 'var(--color-text)' }}>
                    {fmtGw(production)}
                  </span>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}
