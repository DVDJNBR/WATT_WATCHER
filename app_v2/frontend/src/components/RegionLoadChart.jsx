/**
 * RegionLoadChart — bullet-chart style, one row per region: installed
 * capacity (track, full width) vs. current consumption (filled bar), same
 * visual language as CapacityFactorChart's per-source bullets. Sorted by
 * load % (consumption / capacity) descending — this is what makes the
 * outlier jump out (a region can have modest raw consumption and still be
 * the most "loaded" one if it hosts little of its own generation), matching
 * the story the map next to it tells spatially.
 */
import { useMemo } from 'react'

const COLOR = '#3b82f6' // same blue as the map's "Charge" ramp — calm, not alarmist

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
function fmtMw(mw) { return `${Math.round(mw).toLocaleString('fr-FR')} MW` }

/** @param {{ data: Array<{code_insee:string, region:string, value:number, capacity:number}>, loading?: boolean }} props */
export function RegionLoadChart({ data = [], loading = false }) {
  const rows = useMemo(() => {
    return data
      .filter(d => d.capacity > 0)
      .map(d => ({ ...d, pct: Math.min(100, Math.round((d.value / d.capacity) * 100)) }))
      .sort((a, b) => b.pct - a.pct)
  }, [data])

  const track = mix(COLOR, '#171512', 0.22)
  const edge = darken(COLOR, 0.55)

  if (loading) {
    return (
      <section className="glass-card chart-card" data-testid="region-load-loading">
        <h2 className="chart-title">Charge par région</h2>
        <div className="skeleton" style={{ flex: '1 1 0', minHeight: 0 }} />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="glass-card chart-card" data-testid="region-load-empty">
        <h2 className="chart-title">Charge par région</h2>
        <div className="empty-state"><p className="empty-state__title">Aucune donnée disponible</p></div>
      </section>
    )
  }

  return (
    <section className="glass-card chart-card" data-testid="region-load">
      <h2
        className="chart-title"
        title="Consommation actuelle de chaque région face à sa propre capacité installée — le trait plein est la part consommée, le fond est la capacité totale disponible sur place."
      >
        Charge par région
      </h2>
      <div style={{ display: 'flex', gap: 22, marginBottom: 10, fontSize: '0.76rem', color: 'var(--color-text-muted)' }}>
        <span><span style={{ display: 'inline-block', width: 22, height: 10, background: track, borderRadius: 4, marginRight: 6, verticalAlign: 'middle' }} />Capacité installée</span>
        <span><span style={{ display: 'inline-block', width: 22, height: 10, background: COLOR, borderRadius: 4, marginRight: 6, verticalAlign: 'middle' }} />Consommation</span>
      </div>
      <div style={{ flex: '1 1 0', minHeight: 0, overflowY: 'auto' }}>
        {rows.map(({ code_insee, region, value, capacity, pct }) => {
          const narrow = pct < 16
          return (
            <div key={code_insee} style={{ display: 'grid', gridTemplateColumns: '108px 1fr', alignItems: 'center', gap: 14, marginBottom: 12 }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--color-text-muted)', textAlign: 'right', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{region}</span>
              <div style={{ position: 'relative', height: 24 }}>
                <div style={{ position: 'absolute', top: 5, left: 5, right: 0, height: 18, borderRadius: 5, background: track, display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 9 }}>
                  <span style={{ fontSize: '0.65rem', color: '#8a8378' }}>{fmtMw(capacity)}</span>
                </div>
                <div style={{ position: 'absolute', top: 0, left: 0, height: 18, width: `${pct}%`, minWidth: 6, borderRadius: 5, background: COLOR, border: `1px solid ${edge}`, boxSizing: 'border-box', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', paddingRight: 9 }}>
                  {!narrow && <span style={{ fontSize: '0.65rem', fontWeight: 600, color: '#0b1220', whiteSpace: 'nowrap' }}>{pct}%</span>}
                </div>
                {narrow && (
                  <span style={{ position: 'absolute', top: 0, bottom: 0, left: `calc(${pct}% + 10px)`, display: 'flex', alignItems: 'center', fontSize: '0.65rem', color: 'var(--color-text)' }}>
                    {pct}%
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
